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

class DynamicProxyCookieRotator:
    """Класс для динамической ротации прокси с автоматическим получением куки через Anubis challenge"""
    
    def __init__(self, nitter_base_url: str = "https://nitter.tiekoetter.com"):
        # Список прокси без предустановленных куки
        self.proxies = [
            None,  # Без прокси
            "http://user132581:schrvd@37.221.80.162:3542",
            "http://user132581:schrvd@46.149.174.203:3542", 
            "http://user132581:schrvd@37.221.80.181:3542",
            "http://user132581:schrvd@37.221.80.125:3542",
            "http://user132581:schrvd@37.221.80.5:3542",
            "http://user132581:schrvd@213.139.231.127:3542",
            "http://user132581:schrvd@37.221.80.23:3542",
            "http://user132581:schrvd@37.221.80.188:3542",
            "http://user132581:schrvd@45.91.160.28:3542",
        ]
        
        # Кэш куки для каждого прокси {proxy_url: {"cookie": str, "expires": datetime, "valid": bool}}
        self.proxy_cookies = {}
        
        # Базовый URL для Nitter
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
        self.min_fetch_interval = 300  # 5 минут
        
        logger.info(f"🔄 [DYNAMIC] Инициализирован динамический ротатор с {len(self.proxies)} прокси")
    
    def _get_proxy_key(self, proxy: Optional[str]) -> str:
        """Получает ключ для прокси (для использования в словарях)"""
        return proxy if proxy else "NO_PROXY"
    
    def _is_cookie_valid(self, proxy: Optional[str]) -> bool:
        """Проверяет, валиден ли кэшированный куки для прокси"""
        proxy_key = self._get_proxy_key(proxy)
        
        if proxy_key not in self.proxy_cookies:
            return False
            
        cookie_data = self.proxy_cookies[proxy_key]
        
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
        
        # Проверяем минимальный интервал между попытками
        if proxy_key in self.last_cookie_fetch:
            time_since_last = time.time() - self.last_cookie_fetch[proxy_key]
            if time_since_last < self.min_fetch_interval:
                logger.debug(f"⏰ [DYNAMIC] Слишком рано для получения куки для {proxy_key}")
                return None
        
        try:
            logger.info(f"🔍 [DYNAMIC] Получаем новый куки для прокси: {proxy_key}")
            
            # Настраиваем параметры запроса для прокси
            request_kwargs = {}
            if proxy:
                request_kwargs['proxy'] = proxy
            
            # Пытаемся загрузить ПОИСКОВУЮ страницу Nitter (где требуется challenge)
            test_search_url = f"{self.nitter_base_url}/search?f=tweets&q=test&since=&until=&near="
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            async with session.get(test_search_url, headers=headers, timeout=15, **request_kwargs) as response:
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
                        
                        # Сохраняем в кэш
                        self.proxy_cookies[proxy_key] = {
                            "cookie": cookie_string,
                            "expires": datetime.now() + timedelta(hours=12),  # Куки действительны 12 часов
                            "valid": True,
                            "created": datetime.now()
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
                                "created": datetime.now()
                            }
                            
                            logger.info(f"✅ [DYNAMIC] Сохранены anubis куки для {proxy_key}: {len(cookie_string)} символов")
                            return cookie_string
                    
                    logger.info(f"⚪ [DYNAMIC] Нет challenge и anubis куки для {proxy_key}, работаем без куки")
                    # Если нет ни challenge, ни anubis куки
                    self.proxy_cookies[proxy_key] = {
                        "cookie": "",
                        "expires": datetime.now() + timedelta(hours=1),  # Проверяем каждый час
                        "valid": True,
                        "created": datetime.now()
                    }
                    return ""
                    
        except Exception as e:
            logger.error(f"❌ [DYNAMIC] Ошибка получения куки для {proxy_key}: {e}")
            # Обновляем время последней попытки чтобы не спамить
            self.last_cookie_fetch[proxy_key] = time.time()
            
        return None
    
    async def get_proxy_cookie_async(self, session: aiohttp.ClientSession, max_retries: int = 3) -> Tuple[Optional[str], str]:
        """Асинхронно получает связку прокси+куки"""
        attempts = 0
        
        while attempts < len(self.proxies) and attempts < max_retries:
            # Получаем следующий прокси
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            
            proxy_key = self._get_proxy_key(proxy)
            
            # Пропускаем заблокированные прокси
            if proxy_key in self.failed_proxies:
                attempts += 1
                continue
                
            # Пропускаем временно заблокированные прокси
            if proxy_key in self.temp_blocked_proxies:
                unblock_time = self.temp_blocked_proxies[proxy_key]
                if datetime.now() < unblock_time:
                    attempts += 1
                    continue
                else:
                    # Время блокировки истекло, убираем из списка
                    del self.temp_blocked_proxies[proxy_key]
                    logger.info(f"🔓 [DYNAMIC] Прокси {proxy_key} разблокирован после временной блокировки")
            
            # Проверяем кэшированный куки
            if self._is_cookie_valid(proxy):
                cookie = self.proxy_cookies[proxy_key]["cookie"]
                logger.debug(f"🍪 [DYNAMIC] Используем кэшированный куки для {proxy_key}")
                return proxy, cookie
            
            # Пытаемся получить новый куки
            cookie = await self._fetch_cookie_for_proxy(proxy, session)
            if cookie is not None:
                return proxy, cookie
            
            # Если не удалось получить куки, помечаем прокси как временно недоступный
            logger.warning(f"⚠️ [DYNAMIC] Временно блокируем прокси {proxy_key}")
            self.failed_proxies.add(proxy_key)
            attempts += 1
        
        # Если все прокси заблокированы, сбрасываем список и пробуем снова
        if self.failed_proxies:
            logger.warning(f"🔄 [DYNAMIC] Сбрасываем список заблокированных прокси ({len(self.failed_proxies)} шт.)")
            self.failed_proxies.clear()
            
            # Пробуем с первым доступным прокси
            proxy = self.proxies[0]
            self.current_index = 1
            
            cookie = await self._fetch_cookie_for_proxy(proxy, session)
            if cookie is not None:
                return proxy, cookie
        
        # В крайнем случае возвращаем прокси без куки
        logger.error(f"❌ [DYNAMIC] Не удалось получить валидные куки, работаем без них")
        return self.proxies[0], ""
    
    def mark_proxy_failed(self, proxy: Optional[str], cookie: str):
        """Помечает прокси как неработающий"""
        proxy_key = self._get_proxy_key(proxy)
        self.failed_proxies.add(proxy_key)
        
        # Помечаем куки как невалидный
        if proxy_key in self.proxy_cookies:
            self.proxy_cookies[proxy_key]["valid"] = False
            
        logger.warning(f"❌ [DYNAMIC] Прокси {proxy_key} помечен как неработающий")
    
    def mark_proxy_temp_blocked(self, proxy: Optional[str], cookie: str, block_duration_minutes: int = 1):
        """Временно блокирует прокси на заданное количество минут (по умолчанию 1 минута)"""
        proxy_key = self._get_proxy_key(proxy)
        unblock_time = datetime.now() + timedelta(minutes=block_duration_minutes)
        self.temp_blocked_proxies[proxy_key] = unblock_time
        
        # Инвалидируем куки
        if proxy_key in self.proxy_cookies:
            self.proxy_cookies[proxy_key]["valid"] = False
            
        logger.warning(f"😴 [DYNAMIC] Прокси {proxy_key} временно заблокирован на {block_duration_minutes} мин. до {unblock_time.strftime('%H:%M:%S')}")
    
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
        
        return {
            'total_proxies': len(self.proxies),
            'failed_proxies': len(self.failed_proxies),
            'temp_blocked_proxies': active_temp_blocks,
            'available_proxies': len(self.proxies) - len(self.failed_proxies) - active_temp_blocks,
            'cached_cookies': len(self.proxy_cookies),
            'valid_cookies': valid_cookies,
            'expired_cookies': expired_cookies,
            'current_index': self.current_index
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


class DynamicBackgroundProxyCookieRotator(DynamicProxyCookieRotator):
    """Класс для фонового мониторинга с отдельным набором прокси"""
    
    def __init__(self, nitter_base_url: str = "https://nitter.tiekoetter.com"):
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

def mark_proxy_temp_blocked(proxy: Optional[str], cookie: str, block_duration_minutes: int = 1):
    """Временно блокирует прокси на заданное количество минут"""
    dynamic_proxy_cookie_rotator.mark_proxy_temp_blocked(proxy, cookie, block_duration_minutes)

def mark_background_proxy_temp_blocked(proxy: Optional[str], cookie: str, block_duration_minutes: int = 1):
    """Временно блокирует фоновый прокси на заданное количество минут"""
    dynamic_background_proxy_cookie_rotator.mark_proxy_temp_blocked(proxy, cookie, block_duration_minutes)

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