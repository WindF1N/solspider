#!/usr/bin/env python3
"""
Обработчик Anubis challenge для автоматического решения защиты Nitter
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse, urljoin
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 🛡️ УЛУЧШЕННАЯ ОБРАБОТКА СЕТЕВЫХ ОШИБОК С ПЕРЕКЛЮЧЕНИЕМ ДОМЕНОВ
async def robust_network_request(session: aiohttp.ClientSession, 
                                method: str, 
                                url: str, 
                                max_retries: int = 5,
                                switch_domain_on_network_error: bool = True,
                                **kwargs) -> Optional[aiohttp.ClientResponse]:
    """
    Выполняет HTTP запрос с обработкой сетевых ошибок и переключением доменов
    
    Args:
        session: HTTP сессия
        method: HTTP метод (GET, POST)
        url: URL для запроса
        max_retries: Максимальное количество попыток
        switch_domain_on_network_error: Переключать домены при сетевых ошибках
        **kwargs: Дополнительные параметры для запроса
        
    Returns:
        HTTP ответ или None при неудаче
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
    
    current_url = url
    last_error = None
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"🔄 Попытка {attempt + 1}/{max_retries}: {method} {current_url}")
            
            # Выполняем запрос
            if method.upper() == 'GET':
                async with session.get(current_url, **kwargs) as response:
                    await response.read()  # Загружаем содержимое
                    return response
            elif method.upper() == 'POST':
                async with session.post(current_url, **kwargs) as response:
                    await response.read()  # Загружаем содержимое
                    return response
            else:
                raise ValueError(f"Неподдерживаемый HTTP метод: {method}")
                
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Проверяем, является ли это сетевой ошибкой
            is_network_error = any(net_err.lower() in error_str for net_err in NETWORK_ERRORS)
            
            if is_network_error:
                logger.warning(f"🌐 Сетевая ошибка (попытка {attempt + 1}/{max_retries}): {e}")
                
                # Если включено переключение доменов и это не последняя попытка
                if switch_domain_on_network_error and attempt < max_retries - 1:
                    try:
                        # Импортируем функции для переключения доменов
                        from nitter_domain_rotator import get_next_nitter_domain
                        from duplicate_groups_manager import format_nitter_url
                        
                        # Получаем новый домен
                        new_domain = get_next_nitter_domain()
                        
                        # Формируем новый URL с тем же путем
                        parsed_url = urlparse(current_url)
                        new_base_url = format_nitter_url(new_domain)
                        current_url = f"{new_base_url}{parsed_url.path}"
                        if parsed_url.query:
                            current_url += f"?{parsed_url.query}"
                        
                        logger.info(f"🔄 Переключаемся на новый домен: {new_domain}")
                        
                        # Обновляем заголовки для нового домена
                        if 'headers' in kwargs:
                            from duplicate_groups_manager import add_host_header_if_needed
                            add_host_header_if_needed(kwargs['headers'], new_domain)
                        
                    except Exception as domain_error:
                        logger.error(f"❌ Ошибка переключения домена: {domain_error}")
                
                # Экспоненциальная задержка
                backoff_time = min(30, (attempt + 1) * 2 + (attempt * 0.5))
                logger.info(f"⏳ Ждем {backoff_time:.1f}с перед повтором...")
                await asyncio.sleep(backoff_time)
                continue
            else:
                # Не сетевая ошибка - пробрасываем дальше
                raise e
    
    # Если все попытки исчерпаны
    logger.error(f"💀 ВСЕ {max_retries} ПОПЫТОК ИСЧЕРПАНЫ. Последняя ошибка: {last_error}")
    raise last_error

class AnubisHandler:
    """Класс для обработки Anubis challenge и автоматического обновления куки"""
    
    def __init__(self, session: Optional[aiohttp.ClientSession] = None, nitter_domain_rotator=None):
        self.session = session
        self.cookies_updated = False
        self.nitter_domain_rotator = nitter_domain_rotator
        
    async def _anubis_network_request(self, url: str, headers: Dict[str, str], params: Dict[str, Any] = None, max_retries: int = 3) -> Optional[aiohttp.ClientResponse]:
        """
        Специальная функция для сетевых запросов Anubis challenge с обработкой ошибок
        При сетевых ошибках переключает домены через nitter_domain_rotator
        """
        if not self.session:
            logger.error("❌ Нет активной HTTP сессии")
            return None
            
        original_url = url
        current_url = url
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🌐 Попытка {attempt + 1}/{max_retries} для Anubis запроса: {current_url}")
                
                if params:
                    response = await self.session.get(current_url, headers=headers, params=params, allow_redirects=False)
                else:
                    response = await self.session.get(current_url, headers=headers)
                    
                logger.info(f"✅ Anubis запрос успешен, статус: {response.status}")
                return response
                
            except Exception as e:
                error_str = str(e)
                logger.warning(f"⚠️ Ошибка Anubis запроса (попытка {attempt + 1}): {error_str}")
                
                # Проверяем на сетевые ошибки
                network_errors = [
                    "Network is unreachable",
                    "Cannot connect to host",
                    "Connection reset by peer",
                    "Server disconnected",
                    "Connection timeout",
                    "SSL: CERTIFICATE_VERIFY_FAILED",
                    "Can not decode content-encoding: brotli",
                    "503",
                    "502",
                    "bad gateway"
                ]
                
                is_network_error = any(err in error_str for err in network_errors)
                
                if is_network_error and self.nitter_domain_rotator and attempt < max_retries - 1:
                    logger.info(f"🔄 Сетевая ошибка, переключаем домен для Anubis challenge")
                    
                    # Получаем новый домен
                    new_domain = self.nitter_domain_rotator.get_next_domain()
                    if new_domain:
                        # Заменяем домен в URL
                        parsed_url = urlparse(current_url)
                        new_url = current_url.replace(parsed_url.netloc, new_domain)
                        current_url = new_url
                        
                        logger.info(f"🌐 Переключились на новый домен для Anubis: {new_domain}")
                        
                        # Небольшая задержка перед повторной попыткой
                        await asyncio.sleep(1)
                        continue
                    else:
                        logger.error("❌ Не удалось получить новый домен")
                
                # Если это последняя попытка или не сетевая ошибка
                if attempt == max_retries - 1:
                    logger.error(f"❌ Все попытки Anubis запроса исчерпаны: {error_str}")
                    return None
                    
                # Задержка перед следующей попыткой
                await asyncio.sleep(2 ** attempt)
                
        return None

    async def detect_and_solve_challenge(self, url: str, response_text: str, force_fresh_challenge: bool = True) -> Optional[Dict[str, Any]]:
        """
        Обнаруживает Anubis challenge и автоматически решает его
        
        Args:
            url: URL страницы
            response_text: HTML содержимое страницы
            force_fresh_challenge: Всегда получать СВЕЖИЙ challenge (рекомендуется)
            
        Returns:
            Dict с новыми куки если challenge был решен, иначе None
        """
        try:
            # Проверяем, есть ли challenge на странице
            if not self._is_challenge_page(response_text):
                return None
                
            logger.info(f"🔍 Обнаружен Anubis challenge на {url}")
            
            # КРИТИЧНО: Получаем СВЕЖИЙ challenge для избежания 403 ошибок
            if force_fresh_challenge:
                logger.info(f"🔄 Получаем СВЕЖИЙ challenge (устаревшие challenge дают 403)")
                
                if not self.session:
                    logger.error("❌ Нет активной HTTP сессии для получения свежего challenge")
                    return None
                    
                # Делаем новый запрос для получения СВЕЖЕГО challenge
                fresh_headers = {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
                
                # Делаем новый запрос для получения СВЕЖЕГО challenge с обработкой сетевых ошибок
                fresh_response = await self._anubis_network_request(url, fresh_headers)
                if not fresh_response:
                    logger.error(f"❌ Не удалось получить свежий challenge из-за сетевых ошибок")
                    return None
                    
                if fresh_response.status != 200:
                    logger.error(f"❌ Ошибка получения свежего challenge: {fresh_response.status}")
                    fresh_response.close()
                    return None
                    
                fresh_html = await fresh_response.text()
                fresh_response.close()
                
                # Проверяем что challenge все еще нужен
                if not self._is_challenge_page(fresh_html):
                    logger.info("🎉 Challenge больше не требуется - сайт доступен!")
                    return {}
                
                # Используем СВЕЖИЕ данные challenge
                response_text = fresh_html
                logger.info(f"✅ Получен свежий challenge")
            
            # Парсим данные challenge (свежие или оригинальные)
            challenge_data = self._parse_challenge_data(response_text)
            if not challenge_data:
                logger.error("❌ Не удалось извлечь данные challenge")
                return None
                
            # Логируем challenge для отладки
            challenge = challenge_data.get('challenge', 'неизвестен')
            logger.info(f"🎯 Challenge: {challenge}")
                
            # Решаем challenge НЕМЕДЛЕННО
            logger.info(f"⚡ Решаем challenge немедленно...")
            solution = await self._solve_challenge(challenge_data)
            if not solution:
                logger.error("❌ Не удалось решить challenge")
                return None
                
            # Отправляем решение БЕЗ ДОПОЛНИТЕЛЬНЫХ ЗАДЕРЖЕК  
            logger.info(f"🚀 Отправляем решение без задержек...")
            result = await self._submit_solution(url, challenge_data, solution)
            if result:
                status = result.get('status')
                cookies = result.get('cookies', {})
                
                # Проверяем успешные статусы
                if status == 302:
                    if cookies:
                        logger.info(f"✅ Challenge решен! (302) Получены новые куки: {len(cookies)} шт.")
                    else:
                        logger.info(f"✅ Challenge решен! (302) Редирект получен, но куки пустые")
                    self.cookies_updated = True
                    return result
                elif status == 200:
                    response_text = result.get('response_text', '')
                    
                    # Проверяем на временную недоступность сервера
                    if "backend temporarily unavailable" in response_text.lower() or "retrying" in response_text.lower():
                        logger.warning(f"🚫 Сервер Nitter временно недоступен - не проблема нашего кода!")
                        logger.info(f"📋 Это означает что challenge решен правильно, но сервер перегружен")
                        return None  # Временная ошибка - попробуем позже
                    elif cookies:
                        logger.info(f"✅ Challenge решен! (200) Получены новые куки: {len(cookies)} шт.")
                        self.cookies_updated = True
                        return result
                    elif "success" in response_text.lower() or "passed" in response_text.lower():
                        logger.info(f"✅ Challenge возможно решен! (200) Успех в ответе, но куки пустые")
                        self.cookies_updated = True
                        return result
                    else:
                        logger.warning(f"⚠️ Статус 200 но нет признаков успеха. Текст: {response_text[:100]}")
                        return result  # Возвращаем результат для дальнейшего анализа
                else:
                    logger.error(f"❌ Неожиданный статус ответа: {status}")
                    return None
            else:
                logger.error("❌ Не удалось отправить решение")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки Anubis challenge: {e}")
            return None
    
    def _is_challenge_page(self, html_content: str) -> bool:
        """Проверяет, является ли страница Anubis challenge"""
        # Современный challenge может работать БЕЗ текста "Making sure you're not a bot!"
        # Достаточно наличия anubis challenge script
        return ('id="anubis_challenge"' in html_content or 
                "Making sure you're not a bot!" in html_content)
    
    def _parse_challenge_data(self, html_content: str) -> Optional[Dict[str, Any]]:
        """Извлекает данные challenge из HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Ищем script с challenge данными
            challenge_script = soup.find('script', {'id': 'anubis_challenge'})
            if not challenge_script:
                return None
                
            challenge_data = json.loads(challenge_script.get_text())
            
            # Ищем базовый префикс
            base_prefix_script = soup.find('script', {'id': 'anubis_base_prefix'})
            base_prefix = ""
            if base_prefix_script:
                base_prefix = json.loads(base_prefix_script.get_text())
            
            return {
                'challenge': challenge_data.get('challenge'),
                'rules': challenge_data.get('rules', {}),
                'base_prefix': base_prefix
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга challenge: {e}")
            return None
    
    async def _solve_challenge(self, challenge_data: Dict[str, Any]) -> Optional[Tuple[str, int, float]]:
        """Решает proof-of-work challenge"""
        try:
            challenge = challenge_data['challenge']
            rules = challenge_data['rules']
            algorithm = rules.get('algorithm', 'fast')
            difficulty = rules.get('difficulty', 2)
            
            if algorithm != 'fast':
                logger.error(f"Неподдерживаемый алгоритм: {algorithm}")
                return None
            
            logger.info(f"🔧 Решаем challenge: difficulty={difficulty}")
            start_time = time.time()
            
            # Простой proof-of-work алгоритм
            target = "0" * difficulty
            nonce = 0
            max_iterations = 10_000_000
            
            while nonce < max_iterations:
                # Хешируем challenge + nonce
                data = f"{challenge}{nonce}".encode('utf-8')
                hash_hex = hashlib.sha256(data).hexdigest()
                
                if hash_hex.startswith(target):
                    elapsed = time.time() - start_time
                    
                    # ВАЖНО: НЕ добавляем задержку - challenge может протухнуть!
                    logger.info(f"⚡ БЫСТРОЕ РЕШЕНИЕ: Challenge может протухнуть, отправляем немедленно!")
                    
                    logger.info(f"✅ Решение найдено за {elapsed:.2f}s: nonce={nonce}")
                    return hash_hex, nonce, elapsed
                    
                nonce += 1
                
                # Логируем прогресс каждые 100k итераций
                if nonce % 100000 == 0:
                    elapsed = time.time() - start_time
                    speed = nonce / elapsed if elapsed > 0 else 0
                    logger.info(f"🔄 Прогресс: {nonce} итераций, {speed:.0f} H/s")
            
            logger.error(f"❌ Не удалось решить challenge за {max_iterations} итераций")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка решения challenge: {e}")
            return None
    
    async def _submit_solution(self, original_url: str, challenge_data: Dict[str, Any], 
                             solution: Tuple[str, int, float], original_response: Optional[aiohttp.ClientResponse] = None) -> Optional[Dict[str, Any]]:
        """Отправляет решение challenge на сервер"""
        try:
            if not self.session:
                logger.error("Нет активной HTTP сессии")
                return None
                
            hash_result, nonce, elapsed_time = solution
            base_prefix = challenge_data.get('base_prefix', '')
            
            # Формируем URL для отправки
            parsed_url = urlparse(original_url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            submit_url = urljoin(base_url, f"{base_prefix}/.within.website/x/cmd/anubis/api/pass-challenge")
            
            # Формируем реалистичное время (минимум 100ms как в успешном тесте)
            elapsed_ms = max(int(elapsed_time * 1000), 100)
            
            params = {
                'response': hash_result,
                'nonce': str(nonce),
                'redir': original_url,
                'elapsedTime': str(elapsed_ms)
            }
            
            logger.info(f"📤 Отправляем решение на: {submit_url}")
            
            # Формируем заголовки для максимальной похожести на браузер (как в успешном тесте)
            challenge_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Priority': 'u=0, i',
                'Referer': original_url,  # ВАЖНО: Referer должен быть страницей с challenge
                'Sec-CH-UA': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                'Sec-CH-UA-Mobile': '?0',
                'Sec-CH-UA-Platform': '"Linux"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',  # ВАЖНО: добавляем Sec-Fetch-User для навигации
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            }
            
            logger.info(f"🌐 Отправляем с браузерными заголовками для обхода защиты")
            
            # НЕ следуем автоматически за редиректом - обрабатываем вручную с обработкой сетевых ошибок
            response = await self._anubis_network_request(submit_url, challenge_headers, params)
            if not response:
                logger.error(f"❌ Не удалось отправить решение challenge из-за сетевых ошибок")
                return None
                
            logger.info(f"📊 Статус ответа: {response.status}")
            
            # Логируем содержимое ответа для диагностики
            response_text = await response.text()
            logger.info(f"📝 Ответ сервера (первые 200 символов): {response_text[:200]}")
            
            # Извлекаем куки из заголовков
            new_cookies = self._extract_cookies_from_response(response)
            
            # Обрабатываем разные статусы
            if response.status == 302:
                location = response.headers.get('Location')
                logger.info(f"🔄 Редирект на: {location}")
                
                if new_cookies:
                    logger.info(f"✅ Challenge решен успешно! Получены куки для редиректа")
                else:
                    logger.warning(f"⚠️ Редирект без новых куки")
            elif response.status == 200:
                logger.info(f"📋 Статус 200 - анализируем содержимое ответа...")
                
                # Проверяем наличие success сообщений в ответе
                if "success" in response_text.lower() or "passed" in response_text.lower():
                    logger.info(f"✅ Challenge возможно решен (статус 200 + успех в содержимом)")
                else:
                    logger.warning(f"⚠️ Статус 200 но неясно успешность")
            else:
                logger.warning(f"⚠️ Неожиданный статус: {response.status}")
            
            result = {
                'status': response.status,
                'cookies': new_cookies,
                'url': str(response.url),
                'redirect_location': response.headers.get('Location') if response.status == 302 else None,
                'response_text': response_text[:500]  # Первые 500 символов для диагностики
            }
            
            response.close()
            return result
                
        except Exception as e:
            logger.error(f"Ошибка отправки решения: {e}")
            return None
    
    def _extract_cookies_from_response(self, response: aiohttp.ClientResponse) -> Dict[str, str]:
        """Извлекает куки из HTTP ответа"""
        cookies = {}
        try:
            if 'Set-Cookie' in response.headers:
                set_cookie_headers = response.headers.getall('Set-Cookie')
                logger.info(f"🍪 Найдено Set-Cookie заголовков: {len(set_cookie_headers)}")
                
                for i, cookie_header in enumerate(set_cookie_headers):
                    logger.info(f"🍪 Set-Cookie {i+1}: {cookie_header}")
                    
                    # Парсим Set-Cookie заголовок
                    cookie_parts = cookie_header.split(';')
                    if cookie_parts:
                        cookie_pair = cookie_parts[0].strip()
                        if '=' in cookie_pair:
                            name, value = cookie_pair.split('=', 1)
                            name = name.strip()
                            value = value.strip()
                            
                            # Проверяем Max-Age - если 0, то кука удаляется
                            is_deleted = False
                            for part in cookie_parts[1:]:
                                part = part.strip()
                                if part.lower().startswith('max-age='):
                                    max_age = part.split('=', 1)[1].strip()
                                    if max_age == '0':
                                        is_deleted = True
                                        logger.info(f"🗑️ Кука {name} удаляется (Max-Age=0)")
                                        break
                            
                            # Добавляем только неудаленные куки с непустым значением
                            if not is_deleted and value:
                                cookies[name] = value
                                logger.info(f"✅ Сохранена кука: {name}={value[:20]}...")
                            elif is_deleted:
                                # Если кука удаляется, убираем её из результата
                                cookies.pop(name, None)
                                
            logger.info(f"📥 Итого извлечено активных куки: {list(cookies.keys())}")
            
        except Exception as e:
            logger.error(f"Ошибка извлечения куки: {e}")
            
        return cookies
    
    def format_cookies_string(self, cookies: Dict[str, str]) -> str:
        """Форматирует куки в строку для HTTP заголовков"""
        return "; ".join([f"{name}={value}" for name, value in cookies.items()])

async def handle_anubis_challenge_for_session(session: aiohttp.ClientSession, 
                                            url: str, 
                                            response_text: str,
                                            force_fresh_challenge: bool = True,
                                            nitter_domain_rotator=None) -> Optional[Dict[str, str]]:
    """
    Удобная функция для обработки Anubis challenge в существующей сессии
    
    Args:
        session: Активная aiohttp сессия
        url: URL страницы с challenge
        response_text: HTML содержимое страницы
        force_fresh_challenge: Всегда получать СВЕЖИЙ challenge (рекомендуется)
        nitter_domain_rotator: Ротатор доменов для переключения при сетевых ошибках
        
    Returns:
        Словарь с новыми куки или None если challenge не был решен
    """
    handler = AnubisHandler(session, nitter_domain_rotator)
    result = await handler.detect_and_solve_challenge(url, response_text, force_fresh_challenge=force_fresh_challenge)
    
    if result and result.get('cookies'):
        return result['cookies']
    return None

def update_cookies_in_dict(existing_cookies: Dict[str, str], new_cookies: Dict[str, str]) -> Dict[str, str]:
    """
    Обновляет существующий словарь куки новыми значениями
    
    Args:
        existing_cookies: Существующие куки
        new_cookies: Новые куки для добавления/обновления
        
    Returns:
        Обновленный словарь куки
    """
    updated = existing_cookies.copy()
    updated.update(new_cookies)
    return updated

def update_cookies_in_string(existing_cookies_string: str, new_cookies: Dict[str, str]) -> str:
    """
    Обновляет строку куки новыми значениями
    
    Args:
        existing_cookies_string: Существующая строка куки
        new_cookies: Новые куки для добавления
        
    Returns:
        Обновленная строка куки
    """
    # Парсим существующие куки
    existing_dict = {}
    if existing_cookies_string:
        for cookie_pair in existing_cookies_string.split(';'):
            cookie_pair = cookie_pair.strip()
            if '=' in cookie_pair:
                name, value = cookie_pair.split('=', 1)
                existing_dict[name.strip()] = value.strip()
    
    # Обновляем новыми куки
    updated_dict = update_cookies_in_dict(existing_dict, new_cookies)
    
    # Форматируем обратно в строку
    return "; ".join([f"{name}={value}" for name, value in updated_dict.items()])

# Пример интеграции с существующими функциями проекта
async def enhanced_twitter_request_with_anubis(session: aiohttp.ClientSession, 
                                             url: str, 
                                             headers: Dict[str, str],
                                             max_retries: int = 3) -> Optional[aiohttp.ClientResponse]:
    """
    Улучшенная функция запроса к Twitter с автоматическим решением Anubis challenge
    
    Args:
        session: HTTP сессия
        url: URL для запроса
        headers: HTTP заголовки
        max_retries: Максимальное количество попыток
        
    Returns:
        HTTP ответ или None при неудаче
    """
    for attempt in range(max_retries):
        try:
            async with session.get(url, headers=headers) as response:
                content = await response.text()
                
                # Проверяем на Anubis challenge
                if "Making sure you're not a bot!" in content:
                    logger.info(f"🔍 Обнаружен Anubis challenge, попытка {attempt + 1}")
                    
                    # Решаем challenge
                    new_cookies = await handle_anubis_challenge_for_session(session, url, content)
                    
                    if new_cookies:
                        # Обновляем куки в заголовках
                        current_cookies = headers.get('Cookie', '')
                        updated_cookies = update_cookies_in_string(current_cookies, new_cookies)
                        headers['Cookie'] = updated_cookies
                        
                        logger.info(f"✅ Куки обновлены, повторяем запрос")
                        continue  # Повторяем запрос с новыми куки
                    else:
                        logger.error(f"❌ Не удалось решить challenge на попытке {attempt + 1}")
                        
                else:
                    # Обычный ответ, возвращаем его
                    return response
                    
        except Exception as e:
            logger.error(f"Ошибка запроса на попытке {attempt + 1}: {e}")
            
        # Пауза перед следующей попыткой
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
    
    logger.error(f"❌ Не удалось выполнить запрос после {max_retries} попыток")
    return None

if __name__ == "__main__":
    print("🤖 Anubis Challenge Handler - модуль интеграции")
    print("Используйте функции этого модуля для автоматического решения Anubis challenge") 