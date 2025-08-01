#!/usr/bin/env python3
"""
Динамическая система ротации cookies с автоматическим решением Anubis challenge
Убирает предустановленные куки и получает их автоматически для каждого прокси
"""
import logging
import random
import asyncio
import aiohttp
from typing import List, Dict, Optional, Tuple, Any
import time
from datetime import datetime, timedelta
from anubis_handler import AnubisHandler, handle_anubis_challenge_for_session

logger = logging.getLogger(__name__)

# 🛡️ УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ ОБРАБОТКИ ВСЕХ СЕТЕВЫХ ОШИБОК
async def safe_network_request(session, method, url, max_retries=15, **kwargs):
    """
    Универсальная функция для агрессивных повторных попыток при ЛЮБЫХ сетевых ошибках
    """
    NETWORK_ERRORS = [
        "Server disconnected",
        "Connection reset by peer", 
        "Cannot connect to host",
        "Connection timed out",
        "Timeout",
        "SSL", 
        "Name resolution failed",
        "Network is unreachable",
        "Connection refused",
        "Connection aborted",
        "Broken pipe",
        "No route to host",
        "Host is unreachable",
        "Connection closed",
        "Connection lost",
        "Socket error",
        "ClientConnectorError",
        "ClientError",
        "ServerDisconnectedError",
        "ClientOSError"
    ]
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Выполняем HTTP запрос
            if method.lower() == 'get':
                async with session.get(url, **kwargs) as response:
                    await response.read()
                    return response
            elif method.lower() == 'post':
                async with session.post(url, **kwargs) as response:
                    await response.read()
                    return response
            else:
                raise ValueError(f"Unsupported method: {method}")
                
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Проверяем является ли это сетевой ошибкой
            is_network_error = any(net_err.lower() in error_str for net_err in NETWORK_ERRORS)
            
            if is_network_error:
                backoff_time = min(45, (attempt + 1) * 1.5 + random.uniform(0.5, 2))
                logger.warning(f"🔥 [COOKIE] СЕТЕВАЯ ОШИБКА (попытка {attempt + 1}/{max_retries}): {e}")
                logger.warning(f"⏳ [COOKIE] Ждем {backoff_time:.1f}с перед повтором...")
                
                await asyncio.sleep(backoff_time * 2)
                continue
            else:
                # Не сетевая ошибка - пробрасываем дальше
                raise e
    
    # Если все попытки исчерпаны
    logger.error(f"💀 [COOKIE] ВСЕ {max_retries} ПОПЫТОК ИСЧЕРПАНЫ. Последняя ошибка: {last_error}")
    raise last_error

class DynamicProxyCookieRotator:
    """Класс для динамической ротации прокси с автоматическим получением куки через Anubis challenge"""
    
    def __init__(self, nitter_base_url: str = None):
        # Список прокси без предустановленных куки (основные + фоновые)
        self.proxies = [
            None,  # Без прокси
            # Основные прокси
            "http://user132581:schrvd@37.221.80.162:3542",
            "http://user132581:schrvd@46.149.174.203:3542", 
            "http://user132581:schrvd@37.221.80.181:3542",
            "http://user132581:schrvd@37.221.80.125:3542",
            "http://user132581:schrvd@37.221.80.5:3542",
            "http://user132581:schrvd@213.139.231.127:3542",
            "http://user132581:schrvd@37.221.80.23:3542",
            "http://user132581:schrvd@37.221.80.188:3542",
            "http://user132581:schrvd@45.91.160.28:3542",
            # Добавленные фоновые прокси для лучшей ротации
            "http://user132581:schrvd@194.34.250.178:3542",
            "http://user132581:schrvd@149.126.199.210:3542",
            "http://user132581:schrvd@149.126.199.53:3542",
            "http://user132581:schrvd@149.126.211.4:3542",
            "http://user132581:schrvd@149.126.211.208:3542",
            "http://user132581:schrvd@149.126.212.129:3542",
            "http://user132581:schrvd@149.126.240.124:3542",
            "http://user132581:schrvd@149.126.227.154:3542",
            "http://user132581:schrvd@149.126.198.57:3542",
            "http://user132581:schrvd@149.126.198.160:3542",
        ]
        
        # Кэш куки для каждого прокси {proxy_url: {"cookie": str, "expires": datetime, "valid": bool}}
        self.proxy_cookies = {}
        
        # Базовый URL для Nitter - используем динамический выбор домена
        if nitter_base_url is None:
            # Отложенный импорт для избежания циклической зависимости
            try:
                from duplicate_groups_manager import get_nitter_base_url
                self.nitter_base_url = get_nitter_base_url()
            except ImportError:
                # Fallback на IP-адрес если не удается импортировать
                self.nitter_base_url = "http://185.207.1.206:8085"
        else:
            self.nitter_base_url = nitter_base_url
        
        # Индекс текущего прокси для ротации
        self.current_index = 0
        
        # Множество заблокированных прокси
        self.failed_proxies = set()
        
        # Временно заблокированные прокси {proxy_key: unblock_time}
        self.temp_blocked_proxies = {}
        
        # Время последнего получения куки для каждого прокси
        self.last_cookie_fetch = {}
        
        # Минимальное время между попытками получения куки (в секундах)
        self.min_fetch_interval = 1  # 1 секунда (уменьшили для быстрого восстановления)
        
        # 🕒 ВРЕМЯ ПОСЛЕДНЕГО ИСПОЛЬЗОВАНИЯ КАЖДОГО ПРОКСИ (ОТКЛЮЧЕНО)
        self.proxy_last_used = {}  # {proxy_key: timestamp}
        
        # Минимальное время между запросами для одного прокси (в секундах) - ОТКЛЮЧЕНО
        self.proxy_request_interval = 0  # ОТКЛЮЧЕНО: прокси можно использовать сразу
        
        logger.info(f"🔄 [DYNAMIC] Инициализирован динамический ротатор с {len(self.proxies)} прокси")
    
    def _get_proxy_key(self, proxy: Optional[str]) -> str:
        """Получает ключ для прокси (для использования в словарях)"""
        return proxy if proxy else "NO_PROXY"
    
    def _can_use_proxy(self, proxy: Optional[str]) -> bool:
        """Проверяет может ли прокси быть использован (ОТКЛЮЧЕНО - всегда True)"""
        proxy_key = self._get_proxy_key(proxy)
        
        # ОТКЛЮЧЕНО: Всегда возвращаем True, так как proxy_request_interval = 0
        return True
    
    def _mark_proxy_used(self, proxy: Optional[str]):
        """Помечает прокси как использованный (ОТКЛЮЧЕНО - только для статистики)"""
        proxy_key = self._get_proxy_key(proxy)
        self.proxy_last_used[proxy_key] = time.time()
        
        proxy_info = proxy_key if proxy_key != "NO_PROXY" else "БЕЗ ПРОКСИ"
        logger.debug(f"✅ [DYNAMIC] Прокси {proxy_info} использован (блокировка отключена)")
    
    def _is_cookie_valid(self, proxy: Optional[str]) -> bool:
        """Проверяет, валиден ли кэшированный куки для прокси"""
        proxy_key = self._get_proxy_key(proxy)
        
        if proxy_key not in self.proxy_cookies:
            return False
            
        cookie_data = self.proxy_cookies[proxy_key]
        
        # 🔒 ПРОВЕРЯЕМ ЧТО КУКИ ПРИНАДЛЕЖАТ ИМЕННО ЭТОМУ ПРОКСИ
        if cookie_data.get("source_proxy") != proxy_key:
            logger.warning(f"⚠️ [DYNAMIC] Куки для {proxy_key} принадлежат другому прокси: {cookie_data.get('source_proxy')}")
            return False
        
        # Проверяем, не истек ли срок действия
        if cookie_data.get("expires") and datetime.now() > cookie_data["expires"]:
            logger.debug(f"🕒 [DYNAMIC] Куки для {proxy_key} истекли")
            return False
            
        # Проверяем, помечен ли куки как невалидный
        if not cookie_data.get("valid", True):
            logger.debug(f"❌ [DYNAMIC] Куки для {proxy_key} помечены как невалидные")
            return False
            
        return True
    
    async def _fetch_cookie_for_proxy(self, proxy: Optional[str], session: aiohttp.ClientSession) -> Optional[str]:
        """Получает новый куки для прокси через Anubis challenge"""
        proxy_key = self._get_proxy_key(proxy)
        
        # 🔍 ПРОВЕРЯЕМ ТИП NITTER ДОМЕНА
        # IP-адреса (например, 185.207.1.206:8085) не требуют куки Anubis
        # Куки нужны только для доменов типа nitter.tiekoetter.com
        import re
        # Паттерн для IP-адресов с портом (с протоколом или без)
        ip_pattern = r'^(?:https?://)?(\d+\.\d+\.\d+\.\d+:\d+)$'
        
        # Дополнительная проверка: извлекаем домен из URL для анализа
        domain_part = self.nitter_base_url.replace('http://', '').replace('https://', '')
        is_ip_address = re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', domain_part) is not None
        
        if re.match(ip_pattern, self.nitter_base_url) or is_ip_address:
            logger.info(f"🚀 [DYNAMIC] IP-адрес {self.nitter_base_url} (домен: {domain_part}) не требует куки Anubis")
            # Сохраняем пустой куки для IP-адреса
            self.proxy_cookies[proxy_key] = {
                "cookie": "",
                "expires": datetime.now() + timedelta(hours=24),  # IP-адреса стабильны
                "valid": True,
                "created": datetime.now(),
                "proxy_specific": True,
                "source_proxy": proxy_key,
                "ip_address": True  # Флаг что это IP-адрес
            }
            return ""
        
        # # Проверяем минимальный интервал между попытками
        # if proxy_key in self.last_cookie_fetch:
        #     time_since_last = time.time() - self.last_cookie_fetch[proxy_key]
        #     if time_since_last < self.min_fetch_interval:
        #         logger.debug(f"⏰ [DYNAMIC] Слишком рано для получения куки для {proxy_key}")
        #         return None
        
        try:
            logger.info(f"🔍 [DYNAMIC] Получаем новый куки для домена: {self.nitter_base_url}")
            
            # Настраиваем параметры запроса для прокси
            request_kwargs = {}
            if proxy:
                request_kwargs['proxy'] = proxy
            
            # Пытаемся загрузить ПОИСКОВУЮ страницу Nitter (где требуется challenge)
            test_search_url = f"{self.nitter_base_url}/search?f=tweets&q=сиськи&since=&until=&near="
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # 🛡️ ИСПОЛЬЗУЕМ ЗАЩИЩЕННЫЙ HTTP ЗАПРОС ДЛЯ ПОЛУЧЕНИЯ КУКИ
            # Увеличиваем таймаут для медленных прокси
            response = await safe_network_request(session, 'get', test_search_url, 
                                                headers=headers, timeout=60, **request_kwargs)
            content = await response.text()
                
            # Проверяем Set-Cookie заголовки
            set_cookies = response.headers.getall('Set-Cookie', [])
            
            # Проверяем признаки challenge
            has_challenge_text = "Making sure you're not a bot!" in content
            has_anubis_script = 'id="anubis_challenge"' in content
            has_anubis_cookies = any('anubis' in cookie for cookie in set_cookies)
            
            logger.debug(f"🔍 [DYNAMIC] {proxy_key}: статус={response.status}, challenge={has_challenge_text}, anubis_куки={has_anubis_cookies}")
            
            # Проверяем, есть ли Anubis challenge (по script ИЛИ тексту)
            if has_challenge_text or has_anubis_script:
                logger.info(f"🤖 [DYNAMIC] Обнаружен Anubis challenge для {proxy_key}")
                
                # Решаем challenge
                new_cookies = await handle_anubis_challenge_for_session(session, str(response.url), content)
                
                if new_cookies:
                    # Форматируем куки в строку
                    cookie_string = "; ".join([f"{name}={value}" for name, value in new_cookies.items()])
                    
                    # 🔒 СОХРАНЯЕМ УНИКАЛЬНЫЕ КУКИ ДЛЯ КОНКРЕТНОГО ПРОКСИ
                    self.proxy_cookies[proxy_key] = {
                        "cookie": cookie_string,
                        "expires": datetime.now() + timedelta(hours=12),  # Куки действительны 12 часов
                        "valid": True,
                        "created": datetime.now(),
                        "proxy_specific": True,  # Флаг что куки принадлежат конкретному прокси
                        "source_proxy": proxy_key  # Исходный прокси для куки
                    }
                    
                    # Обновляем время последнего получения
                    self.last_cookie_fetch[proxy_key] = time.time()
                    
                    logger.info(f"✅ [DYNAMIC] Получен новый куки для {proxy_key}: {len(cookie_string)} символов")
                    return cookie_string
                else:
                    logger.error(f"❌ [DYNAMIC] Не удалось решить Anubis challenge для {proxy_key}")
                    
            else:
                # Даже если нет полного challenge, проверяем anubis куки
                if has_anubis_cookies:
                    logger.info(f"🍪 [DYNAMIC] Нет полного challenge для {proxy_key}, но есть anubis куки")
                    
                    # Извлекаем anubis куки из заголовков
                    extracted_cookies = {}
                    for cookie_header in set_cookies:
                        if 'anubis' in cookie_header.lower():
                            cookie_parts = cookie_header.split(';')
                            if cookie_parts:
                                cookie_pair = cookie_parts[0].strip()
                                if '=' in cookie_pair:
                                    name, value = cookie_pair.split('=', 1)
                                    extracted_cookies[name.strip()] = value.strip()
                    
                    if extracted_cookies:
                        cookie_string = "; ".join([f"{name}={value}" for name, value in extracted_cookies.items()])
                        
                        self.proxy_cookies[proxy_key] = {
                            "cookie": cookie_string,
                            "expires": datetime.now() + timedelta(hours=6),  # Anubis куки действительны 6 часов
                            "valid": True,
                            "created": datetime.now(),
                            "proxy_specific": True,  # Флаг что куки принадлежат конкретному прокси
                            "source_proxy": proxy_key  # Исходный прокси для куки
                        }
                        
                        logger.info(f"✅ [DYNAMIC] Сохранены anubis куки для {proxy_key}: {len(cookie_string)} символов")
                        return cookie_string
                
                logger.info(f"⚪ [DYNAMIC] Нет challenge и anubis куки для {proxy_key}, работаем без куки")
                # Если нет ни challenge, ни anubis куки
                self.proxy_cookies[proxy_key] = {
                    "cookie": "",
                    "expires": datetime.now() + timedelta(hours=1),  # Проверяем каждый час
                    "valid": True,
                    "created": datetime.now(),
                    "proxy_specific": True,  # Флаг что куки принадлежат конкретному прокси
                    "source_proxy": proxy_key  # Исходный прокси для куки
                }
                return ""
                    
        except Exception as e:
            error_type = type(e).__name__
            error_details = str(e)
            logger.error(f"❌ [DYNAMIC] Ошибка получения куки для {proxy_key}")
            logger.error(f"   📋 Тип ошибки: {error_type}")
            logger.error(f"   📋 Детали: {error_details}")
            logger.error(f"   📋 URL: {test_search_url}")
            
            # Проверяем тип ошибки для принятия решения
            if "Cannot connect to host" in error_details or "Connection" in error_details:
                logger.warning(f"🔌 [DYNAMIC] Проблема соединения для {proxy_key} - возможно прокси недоступен")
            elif "timeout" in error_details.lower():
                logger.warning(f"⏰ [DYNAMIC] Таймаут для {proxy_key} - возможно медленный прокси или проблемы с провайдером")
            elif "SSL" in error_details:
                logger.warning(f"🔒 [DYNAMIC] SSL ошибка для {proxy_key}")
                
            # Обновляем время последней попытки чтобы не спамить
            self.last_cookie_fetch[proxy_key] = time.time()
            
        if error_type == "TimeoutError":
            return "timeout"

        return None
    
    async def get_proxy_cookie_async(self, session: aiohttp.ClientSession, max_retries: int = 3) -> Tuple[Optional[str], str]:
        """Асинхронно получает связку прокси+куки с учётом времени использования (60 секунд между запросами)"""
        max_wait_time = 60  # Максимальное время ожидания в секундах
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            # Проверяем все прокси для поиска доступного
            available_proxies = []
            
            for proxy in self.proxies:
                proxy_key = self._get_proxy_key(proxy)
                
                # Пропускаем заблокированные прокси
                if proxy_key in self.failed_proxies:
                    continue
                    
                # ОТКЛЮЧЕНО: Проверки временных блокировок убраны
                # ОТКЛЮЧЕНО: Проверки времени последнего использования убраны
                # Все прокси всегда доступны (кроме permanently failed)
                available_proxies.append(proxy)
            
            # Если есть доступные прокси
            if available_proxies:
                # 🔄 УСТОЙЧИВАЯ РОТАЦИЯ: перебираем основной список прокси в порядке очереди
                proxy_found = False
                attempts = 0
                
                while not proxy_found and attempts < len(self.proxies):
                    proxy = self.proxies[self.current_index % len(self.proxies)]
                    self.current_index = (self.current_index + 1) % len(self.proxies)
                    attempts += 1
                    
                    proxy_key = self._get_proxy_key(proxy)
                    
                    # Проверяем что прокси доступен (только permanently failed)
                    if proxy_key not in self.failed_proxies:
                        # ОТКЛЮЧЕНО: Проверки временных блокировок и времени использования убраны
                        
                        proxy_found = True
                        break
                
                if not proxy_found:
                    # Если не нашли доступный прокси, берём первый из available_proxies
                    proxy = available_proxies[0]
                
                proxy_key = self._get_proxy_key(proxy)
                
                # Проверяем кэшированный куки И время использования прокси
                if self._is_cookie_valid(proxy) and self._can_use_proxy(proxy):
                    cookie = self.proxy_cookies[proxy_key]["cookie"]
                    # 🕒 ПОМЕЧАЕМ ПРОКСИ КАК ИСПОЛЬЗОВАННЫЙ
                    self._mark_proxy_used(proxy)
                    cookie_info = f"{len(cookie)} символов" if cookie else "пустые"
                    logger.debug(f"🍪 [DYNAMIC] Используем кэшированный куки для {proxy_key} ({cookie_info})")
                    return proxy, cookie
                
                # Пытаемся получить новый куки
                cookie = await self._fetch_cookie_for_proxy(proxy, session)
                if cookie is not None and cookie != "timeout":
                    # 🕒 ПОМЕЧАЕМ ПРОКСИ КАК ИСПОЛЬЗОВАННЫЙ
                    self._mark_proxy_used(proxy)
                    return proxy, cookie
                
                if cookie == "timeout":
                    logger.warning(f"⚠️ [DYNAMIC] Таймаут для {proxy_key}")
                    continue
                
                # Если не удалось получить куки, помечаем прокси как временно недоступный
                logger.warning(f"⚠️ [DYNAMIC] Временно блокируем прокси {proxy_key}")
                self.failed_proxies.add(proxy_key)
                continue
            
            # ОТКЛЮЧЕНО: Больше не ждем освобождения прокси - используем сразу
            # Логика ожидания убрана, так как proxy_request_interval = 0
            
            # Если есть заблокированные прокси и прошло время, сбрасываем их
            if self.failed_proxies:
                logger.warning(f"🔄 [DYNAMIC] Сбрасываем список заблокированных прокси ({len(self.failed_proxies)} шт.)")
                self.failed_proxies.clear()
                continue
            
            # Небольшая пауза перед следующей попыткой
            await asyncio.sleep(0.5)
        
        # Если время ожидания истекло, пробуем любой доступный прокси
        logger.warning(f"⏰ [DYNAMIC] Время ожидания истекло, пробуем любой доступный прокси")
        
        for proxy in self.proxies:
            proxy_key = self._get_proxy_key(proxy)
            
            # Пропускаем заблокированные прокси
            if proxy_key in self.failed_proxies:
                continue
                
            # Пропускаем временно заблокированные прокси
            if proxy_key in self.temp_blocked_proxies:
                unblock_time = self.temp_blocked_proxies[proxy_key]
                if datetime.now() < unblock_time:
                    continue
            
            # Пытаемся получить куки даже если прокси недавно использовался
            cookie = await self._fetch_cookie_for_proxy(proxy, session)
            if cookie is not None:
                self._mark_proxy_used(proxy)
                logger.warning(f"⚠️ [DYNAMIC] Используем прокси {proxy_key} принудительно")
                return proxy, cookie
        
        # В крайнем случае возвращаем без прокси и без куки
        logger.error(f"❌ [DYNAMIC] Не удалось получить валидные куки, работаем без них")
        return None, ""
    
    def mark_proxy_failed(self, proxy: Optional[str], cookie: str):
        """Помечает прокси как неработающий"""
        proxy_key = self._get_proxy_key(proxy)
        self.failed_proxies.add(proxy_key)
        
        # Помечаем куки как невалидный
        if proxy_key in self.proxy_cookies:
            self.proxy_cookies[proxy_key]["valid"] = False
            
        logger.warning(f"❌ [DYNAMIC] Прокси {proxy_key} помечен как неработающий")
    
    def mark_proxy_temp_blocked(self, proxy: Optional[str], cookie: str, block_duration_seconds: int = 120):
        """Временно блокирует прокси (ОТКЛЮЧЕНО - только инвалидируем куки)"""
        proxy_key = self._get_proxy_key(proxy)
        
        # ОТКЛЮЧЕНО: Не блокируем прокси, только инвалидируем куки
        # unblock_time = datetime.now() + timedelta(seconds=block_duration_seconds)
        # self.temp_blocked_proxies[proxy_key] = unblock_time
        
        # Инвалидируем куки для получения новых при следующем запросе
        if proxy_key in self.proxy_cookies:
            self.proxy_cookies[proxy_key]["valid"] = False
            
        logger.info(f"🔄 [DYNAMIC] Прокси {proxy_key} - куки инвалидированы (блокировка отключена)")
    
    def invalidate_cookie(self, proxy: Optional[str]):
        """Инвалидирует куки для прокси (например, при получении 429 ошибки)"""
        proxy_key = self._get_proxy_key(proxy)
        
        if proxy_key in self.proxy_cookies:
            self.proxy_cookies[proxy_key]["valid"] = False
            logger.info(f"🔄 [DYNAMIC] Куки для {proxy_key} инвалидированы")
    
    async def get_cycle_proxy_cookie_async(self, session: aiohttp.ClientSession) -> Tuple[Optional[str], str]:
        """Получает связку прокси+куки для целого цикла работы"""
        proxy, cookie = await self.get_proxy_cookie_async(session)
        proxy_info = "NO_PROXY" if proxy is None else proxy.split('@')[1] if '@' in proxy else proxy
        cookie_info = f"{len(cookie)} символов" if cookie else "без куки"
        logger.info(f"🔄 [DYNAMIC] Связка для цикла: {proxy_info} + куки ({cookie_info})")
        return proxy, cookie
    
    def get_stats(self) -> dict:
        """Возвращает статистику по прокси и куки"""
        valid_cookies = sum(1 for data in self.proxy_cookies.values() if data.get("valid", False))
        expired_cookies = sum(1 for data in self.proxy_cookies.values() 
                            if data.get("expires") and datetime.now() > data["expires"])
        
        # Проверяем активные временные блокировки
        now = datetime.now()
        active_temp_blocks = sum(1 for unblock_time in self.temp_blocked_proxies.values() if now < unblock_time)
        
        # 🕒 Считаем прокси доступные по времени использования
        current_time = time.time()
        available_by_time = 0
        recently_used = 0
        
        for proxy in self.proxies:
            proxy_key = self._get_proxy_key(proxy)
            
            # Пропускаем заблокированные прокси
            if proxy_key in self.failed_proxies or proxy_key in self.temp_blocked_proxies:
                continue
                
            # Проверяем время последнего использования
            if self._can_use_proxy(proxy):
                available_by_time += 1
            else:
                recently_used += 1
        
        # 🔒 Проверяем уникальность куки
        uniqueness_check = self.check_cookie_uniqueness()
        
        return {
            'total_proxies': len(self.proxies),
            'failed_proxies': len(self.failed_proxies),
            'temp_blocked_proxies': active_temp_blocks,
            'available_proxies': len(self.proxies) - len(self.failed_proxies) - active_temp_blocks,
            'available_by_time': available_by_time,  # 🕒 Доступные по времени использования
            'recently_used': recently_used,  # 🕒 Недавно использованные (ждут 60 сек)
            'cached_cookies': len(self.proxy_cookies),
            'valid_cookies': valid_cookies,
            'expired_cookies': expired_cookies,
            'current_index': self.current_index,
            'request_interval': self.proxy_request_interval,  # 🕒 Интервал между запросами
            'cookie_uniqueness': uniqueness_check['is_unique'],  # 🔒 Все ли куки уникальны
            'unique_cookies': uniqueness_check['unique_cookies'],  # 🔒 Количество уникальных куки
            'shared_cookies_count': len(uniqueness_check['shared_cookies'])  # 🔒 Количество повторяющихся куки
        }
    
    def reset_failed_proxies(self):
        """Сбрасывает список заблокированных прокси"""
        failed_count = len(self.failed_proxies)
        self.failed_proxies.clear()
        logger.info(f"🔄 [DYNAMIC] Сброшен список заблокированных прокси (было: {failed_count})")
    
    def cleanup_expired_cookies(self):
        """Очищает истекшие куки из кэша и истекшие временные блокировки"""
        now = datetime.now()
        
        # Очищаем истекшие куки
        expired_cookie_keys = [
            key for key, data in self.proxy_cookies.items()
            if data.get("expires") and now > data["expires"]
        ]
        
        for key in expired_cookie_keys:
            del self.proxy_cookies[key]
            
        # Очищаем истекшие временные блокировки
        expired_block_keys = [
            key for key, unblock_time in self.temp_blocked_proxies.items()
            if now > unblock_time
        ]
        
        for key in expired_block_keys:
            del self.temp_blocked_proxies[key]
            
        if expired_cookie_keys or expired_block_keys:
            logger.info(f"🧹 [DYNAMIC] Очищено: {len(expired_cookie_keys)} истекших куки, {len(expired_block_keys)} истекших блокировок")
    
    def check_cookie_uniqueness(self) -> dict:
        """🔒 Проверяет уникальность куки для каждого прокси"""
        cookie_usage = {}  # cookie_string -> [proxy_keys]
        duplicates = []
        
        for proxy_key, cookie_data in self.proxy_cookies.items():
            cookie_string = cookie_data.get("cookie", "")
            
            # Игнорируем пустые куки
            if not cookie_string:
                continue
                
            if cookie_string not in cookie_usage:
                cookie_usage[cookie_string] = []
            cookie_usage[cookie_string].append(proxy_key)
            
            # Проверяем что source_proxy соответствует ключу
            source_proxy = cookie_data.get("source_proxy")
            if source_proxy != proxy_key:
                duplicates.append({
                    "proxy_key": proxy_key,
                    "source_proxy": source_proxy,
                    "issue": "source_proxy_mismatch"
                })
        
        # Найти куки используемые несколькими прокси
        shared_cookies = {
            cookie_string: proxies for cookie_string, proxies in cookie_usage.items()
            if len(proxies) > 1
        }
        
        return {
            "total_cookies": len([data for data in self.proxy_cookies.values() if data.get("cookie")]),
            "unique_cookies": len(cookie_usage),
            "shared_cookies": shared_cookies,
            "duplicates": duplicates,
            "is_unique": len(shared_cookies) == 0 and len(duplicates) == 0
        }


class DynamicBackgroundProxyCookieRotator(DynamicProxyCookieRotator):
    """Класс для фонового мониторинга с отдельным набором прокси"""
    
    def __init__(self, nitter_base_url: str = None):
        # Инициализируем базовый класс
        super().__init__(nitter_base_url)
        
        # Отдельный набор прокси для фонового мониторинга
        self.proxies = [
            "http://user132581:schrvd@194.34.250.178:3542",
            "http://user132581:schrvd@149.126.199.210:3542",
            "http://user132581:schrvd@149.126.199.53:3542",
            "http://user132581:schrvd@149.126.211.4:3542",
            "http://user132581:schrvd@149.126.211.208:3542",
            "http://user132581:schrvd@149.126.212.129:3542",
            "http://user132581:schrvd@149.126.240.124:3542",
            "http://user132581:schrvd@149.126.227.154:3542",
            "http://user132581:schrvd@149.126.198.57:3542",
            "http://user132581:schrvd@149.126.198.160:3542",
        ]
        
        logger.info(f"🔄 [DYNAMIC_BG] Инициализирован фоновый ротатор с {len(self.proxies)} прокси")


# Синглтоны для использования в проекте
dynamic_proxy_cookie_rotator = DynamicProxyCookieRotator()
dynamic_background_proxy_cookie_rotator = DynamicBackgroundProxyCookieRotator()

# Функции-обертки для совместимости со старым API
async def get_next_proxy_cookie_async(session: aiohttp.ClientSession) -> Tuple[Optional[str], str]:
    """Получает следующую связку прокси+куки асинхронно"""
    return await dynamic_proxy_cookie_rotator.get_proxy_cookie_async(session)

async def get_background_proxy_cookie_async(session: aiohttp.ClientSession) -> Tuple[Optional[str], str]:
    """Получает связку прокси+куки для фонового мониторинга асинхронно"""
    return await dynamic_background_proxy_cookie_rotator.get_proxy_cookie_async(session)

def mark_proxy_failed(proxy: Optional[str], cookie: str):
    """Помечает прокси как неработающий"""
    dynamic_proxy_cookie_rotator.mark_proxy_failed(proxy, cookie)

def mark_background_proxy_failed(proxy: Optional[str], cookie: str):
    """Помечает фоновый прокси как неработающий"""
    dynamic_background_proxy_cookie_rotator.mark_proxy_failed(proxy, cookie)

def mark_proxy_temp_blocked(proxy: Optional[str], cookie: str, block_duration_seconds: int = 120):
    """Временно блокирует прокси на заданное количество секунд"""
    dynamic_proxy_cookie_rotator.mark_proxy_temp_blocked(proxy, cookie, block_duration_seconds)

def mark_background_proxy_temp_blocked(proxy: Optional[str], cookie: str, block_duration_seconds: int = 120):
    """Временно блокирует фоновый прокси на заданное количество секунд"""
    dynamic_background_proxy_cookie_rotator.mark_proxy_temp_blocked(proxy, cookie, block_duration_seconds)

def check_cookie_uniqueness() -> dict:
    """🔒 Проверяет уникальность куки в основном ротаторе"""
    return dynamic_proxy_cookie_rotator.check_cookie_uniqueness()

def get_proxy_stats() -> dict:
    """📊 Получает расширенную статистику по прокси с информацией об уникальности куки"""
    return dynamic_proxy_cookie_rotator.get_stats()

async def get_all_available_proxies_async(session: aiohttp.ClientSession) -> List[Tuple[Optional[str], str]]:
    """Получает ВСЕ доступные прокси+куки для полного перебора при 429 ошибках"""
    all_proxies = []
    
    # Получаем все прокси из ротатора
    total_proxies = len(dynamic_proxy_cookie_rotator.proxies)
    
    # Сохраняем текущий индекс
    original_index = dynamic_proxy_cookie_rotator.current_index
    
    try:
        # Перебираем все прокси
        for i in range(total_proxies):
            proxy = dynamic_proxy_cookie_rotator.proxies[i]
            proxy_key = dynamic_proxy_cookie_rotator._get_proxy_key(proxy)
            
            # Пропускаем навсегда заблокированные прокси
            if proxy_key in dynamic_proxy_cookie_rotator.failed_proxies:
                continue
                
            # Пропускаем временно заблокированные прокси
            if proxy_key in dynamic_proxy_cookie_rotator.temp_blocked_proxies:
                unblock_time = dynamic_proxy_cookie_rotator.temp_blocked_proxies[proxy_key]
                if datetime.now() < unblock_time:
                    continue
                else:
                    # Время блокировки истекло, убираем из списка
                    del dynamic_proxy_cookie_rotator.temp_blocked_proxies[proxy_key]
            
            # Проверяем кэшированный куки
            if dynamic_proxy_cookie_rotator._is_cookie_valid(proxy):
                cookie = dynamic_proxy_cookie_rotator.proxy_cookies[proxy_key]["cookie"]
                all_proxies.append((proxy, cookie))
            else:
                # Пытаемся получить новый куки
                cookie = await dynamic_proxy_cookie_rotator._fetch_cookie_for_proxy(proxy, session)
                if cookie is not None:
                    all_proxies.append((proxy, cookie))
                else:
                    # Если не удалось получить куки, добавляем с пустым cookie
                    all_proxies.append((proxy, ""))
        
        logger.info(f"🔄 [DYNAMIC] Получено {len(all_proxies)} доступных прокси из {total_proxies} общих")
        return all_proxies
        
    finally:
        # Восстанавливаем исходный индекс
        dynamic_proxy_cookie_rotator.current_index = original_index

# Функция для периодической очистки
async def cleanup_task():
    """Задача для периодической очистки истекших куки"""
    while True:
        try:
            dynamic_proxy_cookie_rotator.cleanup_expired_cookies()
            dynamic_background_proxy_cookie_rotator.cleanup_expired_cookies()
            await asyncio.sleep(3600)  # Очищаем каждый час
        except Exception as e:
            logger.error(f"❌ Ошибка в задаче очистки: {e}")
            await asyncio.sleep(600)  # При ошибке ждем 10 минут

if __name__ == "__main__":
    print("🔄 Динамическая система ротации куки с Anubis challenge")
    print("Используйте функции этого модуля для автоматического получения куки") 