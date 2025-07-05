#!/usr/bin/env python3
"""
🌟 VIP TWITTER MONITOR 🌟
Независимый парсер VIP аккаунтов Twitter для мгновенных сигналов

Функциональность:
- Мониторинг VIP Twitter аккаунтов в реальном времени
- Поиск контрактов в твитах
- Автоматическая покупка для указанных аккаунтов
- Отправка VIP уведомлений в отдельного Telegram бота
- Работает независимо от основной системы SolSpider
"""

import os
import asyncio
import aiohttp
import requests
import logging
import time
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Set, Tuple
import re
import json

# Добавляем динамическую систему куки с Anubis handler
from dynamic_cookie_rotation import get_background_proxy_cookie_async
from anubis_handler import handle_anubis_challenge_for_session

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

# Импортируем конфигурацию
try:
    from vip_config import (
        VIP_TWITTER_ACCOUNTS, VIP_MONITOR_SETTINGS, VIP_TELEGRAM_CONFIG,
        VIP_NITTER_COOKIES, VIP_PROXIES, AUTO_BUY_CONFIG, format_vip_message, create_keyboard,
        get_active_accounts, get_auto_buy_accounts, get_gas_fee, get_gas_description
    )
except ImportError:
    print("❌ Не удалось импортировать vip_config.py")
    print("Убедитесь что файл vip_config.py находится в той же папке")
    exit(1)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, VIP_MONITOR_SETTINGS.get('log_level', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vip_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('VIPMonitor')

class VipTwitterMonitor:
    """Независимый мониторинг VIP Twitter аккаунтов"""
    
    def __init__(self):
        # Загружаем конфигурацию
        self.VIP_ACCOUNTS = VIP_TWITTER_ACCOUNTS
        self.monitor_settings = VIP_MONITOR_SETTINGS
        self.telegram_config = VIP_TELEGRAM_CONFIG
        self.auto_buy_config = AUTO_BUY_CONFIG
        
        # Настройки Telegram VIP бота
        self.VIP_BOT_TOKEN = self.telegram_config['bot_token']
        self.VIP_CHAT_ID = os.getenv(self.telegram_config['chat_id_env_var'])
        
        # Кэш для дедупликации сигналов
        self.signals_cache: Set[str] = set()
        
        # Настройки мониторинга
        self.check_interval = self.monitor_settings['default_check_interval']
        self.max_retries = self.monitor_settings['max_retries']
        
        # Используем динамическую систему куки вместо статичных VIP_NITTER_COOKIES
        self.proxies = VIP_PROXIES
        self.current_proxy_index = 0
        
        active_count = sum(1 for config in self.VIP_ACCOUNTS.values() if config.get('enabled', False))
        proxy_count = len([p for p in self.proxies if p is not None])
        
        logger.info(f"🌟 VIP Twitter Monitor инициализирован с {active_count} активными аккаунтами")
        logger.info(f"🔄 Используем динамическую систему куки + {proxy_count} прокси ({len(self.proxies)} всего)")
        
        if not self.VIP_CHAT_ID:
            logger.error(f"❌ {self.telegram_config['chat_id_env_var']} не задан в переменных окружения!")
    
    async def get_next_cookie_async(self, session: aiohttp.ClientSession) -> Tuple[Optional[str], str]:
        """Получает динамические cookies через новую систему с автоматическим решением Anubis challenge"""
        return await get_background_proxy_cookie_async(session)
    
    def get_next_proxy(self) -> Optional[str]:
        """Получает следующий прокси для ротации"""
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return proxy
    
    def get_proxy_connector(self, proxy_url: Optional[str]):
        """Создает прокси-коннектор для aiohttp"""
        if not proxy_url:
            return None
            
        try:
            import aiohttp_socks
            from aiohttp_socks import ProxyType, ProxyConnector
            
            if proxy_url.startswith('socks5://'):
                # SOCKS5 прокси
                proxy_parts = proxy_url.replace('socks5://', '').split('@')
                if len(proxy_parts) == 2:
                    auth_part, host_part = proxy_parts
                    user, password = auth_part.split(':')
                    host, port = host_part.split(':')
                    return ProxyConnector(
                        proxy_type=ProxyType.SOCKS5,
                        host=host,
                        port=int(port),
                        username=user,
                        password=password
                    )
                else:
                    host, port = proxy_parts[0].split(':')
                    return ProxyConnector(
                        proxy_type=ProxyType.SOCKS5,
                        host=host,
                        port=int(port)
                    )
            elif proxy_url.startswith('http://'):
                # HTTP прокси - используем стандартный способ aiohttp
                return None  # Для HTTP прокси используем параметр proxy в session.get()
            else:
                logger.warning(f"⚠️ Неподдерживаемый тип прокси: {proxy_url}")
                return None
                
        except ImportError:
            logger.warning("⚠️ aiohttp-socks не установлен, SOCKS прокси недоступны")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка создания прокси-коннектора: {e}")
            return None
    
    def extract_contracts_from_text(self, text: str) -> List[str]:
        """Извлекает Solana контракты из текста твита"""
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
                clean_contracts.append(contract)
        
        return list(set(clean_contracts))  # Убираем дубликаты
    
    def extract_clean_text(self, element) -> str:
        """Извлекает чистый текст из HTML элемента твита включая все скрытые контракты"""
        try:
            all_text_parts = []
            
            # 1. Основной текст элемента
            main_text = element.get_text(separator=' ', strip=True)
            if main_text:
                all_text_parts.append(main_text)
            
            # 2. 🔗 ИЗВЛЕКАЕМ ТЕКСТ ИЗ ВСЕХ ССЫЛОК
            for link in element.find_all('a'):
                # Текст ссылки
                link_text = link.get_text(strip=True)
                if link_text and link_text not in all_text_parts:
                    all_text_parts.append(link_text)
                
                # href атрибут ссылки
                href = link.get('href', '')
                if href and href not in all_text_parts:
                    all_text_parts.append(href)
                    logger.debug(f"🔗 Найден href: {href[:50]}...")
                
                # title атрибут ссылки
                title = link.get('title', '')
                if title and title not in all_text_parts:
                    all_text_parts.append(title)
            
            # 3. 🖼️ ИЗВЛЕКАЕМ ДАННЫЕ ИЗ ИЗОБРАЖЕНИЙ
            for img in element.find_all('img'):
                # alt текст изображения
                alt_text = img.get('alt', '')
                if alt_text and alt_text not in all_text_parts:
                    all_text_parts.append(alt_text)
                    logger.debug(f"🖼️ Найден alt: {alt_text[:50]}...")
                
                # src изображения (может содержать контракт в имени)
                src = img.get('src', '')
                if src and src not in all_text_parts:
                    all_text_parts.append(src)
                
                # data-url атрибуты
                data_url = img.get('data-url', '')
                if data_url and data_url not in all_text_parts:
                    all_text_parts.append(data_url)
            
            # 4. 🎬 ИЗВЛЕКАЕМ ДАННЫЕ ИЗ ВИДЕО
            for video in element.find_all('video'):
                # poster изображение видео
                poster = video.get('poster', '')
                if poster and poster not in all_text_parts:
                    all_text_parts.append(poster)
                
                # data-url видео
                data_url = video.get('data-url', '')
                if data_url and data_url not in all_text_parts:
                    all_text_parts.append(data_url)
                    logger.debug(f"🎬 Найден video data-url: {data_url[:50]}...")
            
            # 5. 📋 ИЗВЛЕКАЕМ ДАННЫЕ ИЗ КАРТОЧЕК
            for card in element.find_all('div', class_='card'):
                # Заголовок карточки
                card_title = card.find('h2', class_='card-title')
                if card_title:
                    title_text = card_title.get_text(strip=True)
                    if title_text and title_text not in all_text_parts:
                        all_text_parts.append(title_text)
                
                # Описание карточки
                card_desc = card.find('p', class_='card-description')
                if card_desc:
                    desc_text = card_desc.get_text(strip=True)
                    if desc_text and desc_text not in all_text_parts:
                        all_text_parts.append(desc_text)
                
                # URL карточки
                card_link = card.find('a', class_='card-container')
                if card_link:
                    card_href = card_link.get('href', '')
                    if card_href and card_href not in all_text_parts:
                        all_text_parts.append(card_href)
                        logger.debug(f"📋 Найден card href: {card_href[:50]}...")
            
            # 6. 🏷️ ИЗВЛЕКАЕМ ВСЕ DATA-АТРИБУТЫ
            for elem in element.find_all():
                for attr_name, attr_value in elem.attrs.items():
                    if attr_name.startswith('data-') and isinstance(attr_value, str):
                        if attr_value and attr_value not in all_text_parts:
                            all_text_parts.append(attr_value)
                            logger.debug(f"🏷️ Найден {attr_name}: {attr_value[:50]}...")
            
            # 7. 📎 ИЗВЛЕКАЕМ ТЕКСТ ИЗ ATTACHMENTS
            attachments = element.find_all('div', class_='attachments')
            for attachment in attachments:
                attachment_text = attachment.get_text(strip=True)
                if attachment_text and attachment_text not in all_text_parts:
                    all_text_parts.append(attachment_text)
            
            # 8. 🔍 ИЗВЛЕКАЕМ СКРЫТЫЙ ТЕКСТ ИЗ SPAN И DIV
            for span in element.find_all(['span', 'div']):
                # Проверяем атрибуты title, aria-label и другие
                for attr in ['title', 'aria-label', 'data-original-title']:
                    attr_value = span.get(attr, '')
                    if attr_value and attr_value not in all_text_parts:
                        all_text_parts.append(attr_value)
            
            # Добавляем пробелы между элементами для корректной обработки
            for link in element.find_all('a'):
                if link.string:
                    if link.previous_sibling and not str(link.previous_sibling).endswith(' '):
                        link.insert_before(' ')
                    if link.next_sibling and not str(link.next_sibling).startswith(' '):
                        link.insert_after(' ')
            
            # Объединяем весь найденный текст
            full_text = " ".join(all_text_parts)
            
            # Очищаем от множественных пробелов и лишних символов
            full_text = re.sub(r'\s+', ' ', full_text).strip()
            
            logger.debug(f"🔍 Twitter: извлечено {len(all_text_parts)} частей текста: {full_text[:100]}...")
            
            return full_text
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения Twitter текста: {e}")
            # Возвращаем базовый текст как fallback
            return element.get_text(strip=True)
    
    async def send_vip_notification(self, message: str, keyboard: Optional[List] = None) -> bool:
        """Отправляет VIP уведомление в Telegram"""
        try:
            payload = {
                "chat_id": self.VIP_CHAT_ID,
                "text": message,
                "parse_mode": self.telegram_config['parse_mode'],
                "disable_web_page_preview": self.telegram_config['disable_web_page_preview']
            }
            
            if keyboard:
                payload["reply_markup"] = {"inline_keyboard": keyboard}
            
            url = f"https://api.telegram.org/bot{self.VIP_BOT_TOKEN}/sendMessage"
            response = requests.post(url, json=payload, timeout=self.telegram_config['timeout'])
            
            if response.status_code == 200:
                logger.info("✅ VIP уведомление отправлено")
                return True
            else:
                logger.error(f"❌ Ошибка отправки VIP уведомления: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Критическая ошибка отправки VIP уведомления: {e}")
            return False
    
    async def send_vip_photo_notification(self, photo_url: str, caption: str, keyboard: Optional[List] = None) -> bool:
        """Отправляет VIP уведомление с фото в Telegram"""
        try:
            payload = {
                "chat_id": self.VIP_CHAT_ID,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": self.telegram_config['parse_mode']
            }
            
            if keyboard:
                payload["reply_markup"] = {"inline_keyboard": keyboard}
            
            url = f"https://api.telegram.org/bot{self.VIP_BOT_TOKEN}/sendPhoto"
            response = requests.post(url, json=payload, timeout=self.telegram_config['timeout'])
            
            if response.status_code == 200:
                logger.info("✅ VIP фото уведомление отправлено")
                return True
            else:
                # Если фото не получилось, отправляем текст
                logger.warning(f"⚠️ Не удалось отправить фото, отправляю текст: {response.text}")
                return await self.send_vip_notification(caption, keyboard)
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки VIP фото: {e}")
            return await self.send_vip_notification(caption, keyboard)
    
    async def execute_automatic_purchase(self, contract: str, username: str, tweet_text: str, amount_sol: float) -> Dict:
        """Выполняет автоматическую покупку токена"""
        logger.info(f"🚀 АВТОМАТИЧЕСКАЯ ПОКУПКА: {contract} на {amount_sol} SOL от @{username}")
        
        import time
        start_time = time.time()
        
        # Проверяем настройки автопокупки
        if self.auto_buy_config.get('simulate_only', True):
            logger.info("💡 Режим симуляции - реальная покупка не выполняется")
            
            # Симуляция покупки
            try:
                await asyncio.sleep(2)  # Имитация времени выполнения
                
                # Случайный результат для демонстрации
                import random
                success = random.choice([True, False])
                
                if success:
                    return {
                        'success': True,
                        'tx_hash': f"mock_tx_{int(time.time())}",
                        'sol_amount': amount_sol,
                        'execution_time': 2.0,
                        'status': 'Симуляция - успешно выполнено'
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Mock error: insufficient balance',
                        'execution_time': 2.0
                    }
                    
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Critical error: {str(e)}',
                    'execution_time': 0
                }
        else:
            # 🚀 РЕАЛЬНАЯ АВТОПОКУПКА через Axiom.trade
            logger.info(f"💰 ВЫПОЛНЯЕМ РЕАЛЬНУЮ ПОКУПКУ через {self.auto_buy_config.get('trading_platform', 'axiom')}")
            
            try:
                # Используем SOL напрямую без конвертации
                sol_amount = amount_sol
                
                # Импортируем Axiom трейдер если есть
                try:
                    from axiom_trader import execute_axiom_purchase
                    
                    # Выполняем реальную покупку через Axiom.trade
                    # 🔥 Определяем тип газа на основе приоритета VIP аккаунта
                    account_priority = account_config.get('priority', 'HIGH')
                    if account_priority == 'ULTRA':
                        gas_type = 'ultra_vip'  # $5 газ для ULTRA приоритета
                    else:
                        gas_type = 'vip_signals'  # $2 газ для HIGH приоритета
                    
                    vip_gas_fee = get_gas_fee(gas_type)
                    gas_description = get_gas_description(gas_type)
                    
                    logger.info(f"🔥 Используем {gas_description}")
                    logger.info(f"⚡ VIP Gas fee: {vip_gas_fee} SOL (~${vip_gas_fee * 140:.2f})")
                    
                    result = await execute_axiom_purchase(
                        contract_address=contract,
                        twitter_username=username,
                        tweet_text=tweet_text,
                        sol_amount=sol_amount,
                        slippage=self.auto_buy_config.get('slippage_percent', 15),
                        priority_fee=vip_gas_fee  # 🔥 VIP газ для быстрого подтверждения
                    )
                    
                    execution_time = time.time() - start_time
                    
                    if result.get('success', False):
                        logger.info(f"✅ Автопокупка успешна! TX: {result.get('tx_hash', 'N/A')}")
                        return {
                            'success': True,
                            'tx_hash': result.get('tx_hash', 'N/A'),
                            'sol_amount': sol_amount,
                            'execution_time': execution_time,
                            'status': f'Axiom.trade - покупка {sol_amount:.6f} SOL',
                            'platform': 'Axiom.trade'
                        }
                    else:
                        error_msg = result.get('error', 'Unknown error from Axiom')
                        logger.error(f"❌ Ошибка автопокупки: {error_msg}")
                        return {
                            'success': False,
                            'error': error_msg,
                            'execution_time': execution_time
                        }
                        
                except ImportError:
                    logger.error("❌ axiom_trader модуль не найден! Установите Axiom интеграцию")
                    return {
                        'success': False,
                        'error': 'axiom_trader module not found',
                        'execution_time': time.time() - start_time
                    }
                    
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"❌ Критическая ошибка автопокупки: {e}")
                return {
                    'success': False,
                    'error': f'Critical error: {str(e)}',
                    'execution_time': execution_time
                }
    
    async def check_twitter_account(self, username: str, account_config: Dict) -> List[Dict]:
        """Проверяет один Twitter аккаунт на наличие контрактов с динамической системой куки и Anubis handler"""
        contracts_found = []
        
        try:
            proxy_url = self.get_next_proxy()
            
            logger.info(f"🌟 Проверяем VIP аккаунт @{username}... (прокси: {'✅' if proxy_url else '❌'})")
            
            # URL профиля на Nitter
            url = f"https://nitter.tiekoetter.com/{username}"
            timeout = self.monitor_settings['request_timeout']
            
            # Создаем коннектор с прокси (если нужен)
            connector = self.get_proxy_connector(proxy_url)
            
            # Параметры для session
            session_kwargs = {}
            if connector:
                session_kwargs['connector'] = connector
            
            async with aiohttp.ClientSession(**session_kwargs) as session:
                # Получаем динамические cookies через новую систему
                dynamic_proxy, cookies_string = await self.get_next_cookie_async(session)
                
                if not cookies_string:
                    logger.error(f"❌ Не удалось получить cookies для @{username}")
                    return contracts_found
                
                # Парсим строку cookies в словарь для aiohttp
                cookies = {}
                try:
                    for cookie_part in cookies_string.split(';'):
                        if '=' in cookie_part:
                            key, value = cookie_part.strip().split('=', 1)
                            cookies[key] = value
                except Exception as e:
                    logger.error(f"❌ Ошибка парсинга cookies для @{username}: {e}")
                    return contracts_found
                
                # Заголовки
                headers = {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                # Параметры для запроса
                request_kwargs = {
                    'headers': headers,
                    'cookies': cookies,
                    'timeout': timeout
                }
                
                # Для HTTP прокси используем параметр proxy
                if proxy_url and proxy_url.startswith('http://'):
                    request_kwargs['proxy'] = proxy_url
                
                async with session.get(url, **request_kwargs) as response:
                    html = await response.text()
                    
                    # 🔍 ПРОВЕРЯЕМ НА ANUBIS CHALLENGE
                    if ('id="anubis_challenge"' in html or "Making sure you're not a bot!" in html):
                        logger.warning(f"🚫 Обнаружен Anubis challenge для @{username} - автоматически решаем...")
                        
                        try:
                            # Автоматически решаем challenge
                            new_cookies = await handle_anubis_challenge_for_session(
                                session, url, html, force_fresh_challenge=True
                            )
                            
                            if new_cookies:
                                logger.info(f"✅ Challenge решен для @{username}, повторяем запрос...")
                                
                                # Обновляем cookies и повторяем запрос
                                for key, value in new_cookies.items():
                                    cookies[key] = value
                                request_kwargs['cookies'] = cookies
                                    
                                async with session.get(url, **request_kwargs) as retry_response:
                                    if retry_response.status == 200:
                                        html = await retry_response.text()
                                        logger.info(f"✅ VIP аккаунт @{username} успешно загружен после решения challenge")
                                    else:
                                        logger.warning(f"⚠️ Ошибка после challenge @{username}: {retry_response.status}")
                                        return contracts_found
                            else:
                                logger.error(f"❌ Не удалось решить challenge для @{username}")
                                return contracts_found
                                
                        except Exception as challenge_error:
                            logger.error(f"❌ Ошибка решения challenge для @{username}: {challenge_error}")
                            return contracts_found
                    
                    elif response.status != 200:
                        logger.warning(f"⚠️ Ошибка доступа к @{username}: HTTP {response.status}")
                        return contracts_found
                    
                    # Парсим HTML и ищем контракты
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Находим твиты
                    tweets = soup.find_all('div', class_='timeline-item')
                    logger.info(f"📱 Найдено {len(tweets)} твитов у @{username}")
                    
                    for tweet in tweets:
                        # Пропускаем ретвиты
                        if tweet.find('div', class_='retweet-header'):
                            continue
                        
                        # Получаем содержимое твита
                        tweet_content = tweet.find('div', class_='tweet-content')
                        if not tweet_content:
                            continue
                        
                        # Извлекаем текст
                        tweet_text = self.extract_clean_text(tweet_content)
                        
                        # Ищем контракты
                        contracts = self.extract_contracts_from_text(tweet_text)
                        
                        for contract in contracts:
                            # Проверяем дедупликацию
                            signal_key = f"{username}:{contract}"
                            
                            if signal_key not in self.signals_cache:
                                self.signals_cache.add(signal_key)
                                contracts_found.append({
                                    'contract': contract,
                                    'tweet_text': tweet_text,
                                    'username': username,
                                    'account_config': account_config
                                })
                                logger.info(f"🔥 VIP КОНТРАКТ НАЙДЕН! @{username}: {contract}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка проверки @{username}: {e}")
        
        return contracts_found
    
    async def process_contract_signal(self, signal_data: Dict):
        """Обрабатывает найденный контракт и отправляет уведомления"""
        contract = signal_data['contract']
        tweet_text = signal_data['tweet_text']
        username = signal_data['username']
        account_config = signal_data['account_config']
        
        logger.info(f"🔥 Обрабатываем VIP сигнал: {contract} от @{username}")
        
        # Автоматическая покупка если включена
        purchase_result = None
        if account_config.get('auto_buy', False):
            amount_sol = account_config.get('buy_amount_sol', self.auto_buy_config['default_amount_sol'])
            purchase_result = await self.execute_automatic_purchase(
                contract, username, tweet_text, amount_sol
            )
        
        # Создаем VIP уведомление используя шаблон
        message = self.format_vip_signal_message(
            contract, username, tweet_text, account_config, purchase_result
        )
        
        # Создаем клавиатуру
        keyboard = create_keyboard(contract)
        
        # Отправляем уведомление (с попыткой отправить фото)
        photo_url = f"https://axiomtrading.sfo3.cdn.digitaloceanspaces.com/{contract}.webp"
        success = await self.send_vip_photo_notification(photo_url, message, keyboard)
        
        if success:
            logger.info(f"📤 VIP сигнал отправлен для {contract} от @{username}")
        else:
            logger.error(f"❌ Не удалось отправить VIP сигнал для {contract}")
    
    def format_vip_signal_message(self, contract: str, username: str, tweet_text: str, 
                                 account_config: Dict, purchase_result: Optional[Dict] = None) -> str:
        """Форматирует VIP сообщение используя шаблон"""
        # Обрезаем твит если слишком длинный
        if len(tweet_text) > 200:
            tweet_text = tweet_text[:200] + "..."
        
        # Базовое сообщение
        message = format_vip_message(
            'contract_found',
            description=account_config['description'],
            username=username,
            contract=contract,
            tweet_text=tweet_text,
            priority=account_config['priority'],
            timestamp=datetime.now().strftime('%H:%M:%S')
        )
        
        # Добавляем информацию об автоматической покупке
        if purchase_result:
            if purchase_result['success']:
                message += format_vip_message(
                    'auto_buy_success',
                    status=purchase_result['status'],
                    sol_amount=purchase_result['sol_amount'],
                    execution_time=purchase_result['execution_time'],
                    tx_hash=purchase_result['tx_hash']
                )
            else:
                message += format_vip_message(
                    'auto_buy_error',
                    error=purchase_result['error'][:100]
                )
        elif account_config.get('auto_buy', False):
            message += format_vip_message('auto_buy_enabled')
        
        return message
    
    async def monitor_loop(self):
        """Основной цикл мониторинга VIP аккаунтов"""
        logger.info("🚀 Запуск VIP мониторинга Twitter аккаунтов...")
        
        while True:
            try:
                start_time = time.time()
                
                # Проверяем все активные VIP аккаунты
                tasks = []
                for username, config in self.VIP_ACCOUNTS.items():
                    if config.get('enabled', False):
                        task = self.check_twitter_account(username, config)
                        tasks.append(task)
                
                if tasks:
                    # Выполняем проверку всех аккаунтов параллельно
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Обрабатываем найденные контракты
                    for result in results:
                        if isinstance(result, list):
                            for signal_data in result:
                                await self.process_contract_signal(signal_data)
                        elif isinstance(result, Exception):
                            logger.error(f"❌ Ошибка в задаче мониторинга: {result}")
                
                # Статистика цикла
                cycle_time = time.time() - start_time
                logger.info(f"🔄 VIP мониторинг завершен за {cycle_time:.2f}с. Непрерывная проверка...")
                
                # Очищаем кэш при превышении лимита
                cleanup_threshold = self.monitor_settings['cache_cleanup_threshold']
                if len(self.signals_cache) > cleanup_threshold:
                    logger.info("🧹 Очистка кэша сигналов")
                    self.signals_cache.clear()
                
                # Минимальная пауза для предотвращения перегрузки
                await asyncio.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Остановка VIP мониторинга по запросу пользователя")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в цикле VIP мониторинга: {e}")
                await asyncio.sleep(10)  # Пауза перед повторной попыткой
    
    async def start(self):
        """Запуск VIP мониторинга"""
        if not self.VIP_CHAT_ID:
            logger.error(f"❌ {self.telegram_config['chat_id_env_var']} не настроен. Мониторинг не может быть запущен.")
            return
        
        # Отправляем уведомление о запуске если включено
        if self.monitor_settings.get('send_startup_notification', True):
            active_accounts = get_active_accounts()
            auto_buy_accounts = get_auto_buy_accounts()
            
            start_message = format_vip_message(
                'startup',
                active_accounts=len(active_accounts),
                auto_buy_accounts=', '.join([f'@{name}' for name in auto_buy_accounts.keys()]),
                timestamp=datetime.now().strftime('%H:%M:%S %d.%m.%Y')
            )
            
            await self.send_vip_notification(start_message)
        
        # Запускаем основной цикл
        await self.monitor_loop()


async def main():
    """Главная функция"""
    monitor = VipTwitterMonitor()
    await monitor.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 VIP Twitter Monitor остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.exception("Критическая ошибка в VIP мониторе")