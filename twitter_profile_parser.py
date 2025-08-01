#!/usr/bin/env python3
"""
Парсер профилей авторов твитов с Nitter
"""

import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from dynamic_cookie_rotation import get_background_proxy_cookie_async
from anubis_handler import handle_anubis_challenge_for_session

logger = logging.getLogger(__name__)

class TwitterProfileParser:
    """Парсер профилей авторов твитов"""
    
    def __init__(self):
        self.session = None
        # Убираем старый cookie_rotator - используем динамическую систему с Anubis handler
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def parse_number(self, text):
        """Парсит число из текста (поддерживает K, M форматы)"""
        if not text:
            return 0
            
        text = text.replace(',', '').strip()
        
        # Удаляем лишние символы
        text = re.sub(r'[^\d.KMBkmb]', '', text)
        
        if not text:
            return 0
        
        try:
            # Обрабатываем сокращения
            if text.upper().endswith('K'):
                return int(float(text[:-1]) * 1000)
            elif text.upper().endswith('M'):
                return int(float(text[:-1]) * 1000000)
            elif text.upper().endswith('B'):
                return int(float(text[:-1]) * 1000000000)
            else:
                return int(float(text))
        except (ValueError, IndexError):
            return 0
    
    def extract_clean_text(self, element):
        """Извлекает чистый текст из HTML элемента с правильными разделителями"""
        try:
            # Создаём копию элемента для безопасной модификации
            element_copy = element.__copy__()
            
            # Добавляем пробелы перед ссылками и другими элементами
            for link in element_copy.find_all('a'):
                if link.string:
                    # Добавляем пробел перед ссылкой если его нет
                    if link.previous_sibling and not str(link.previous_sibling).endswith(' '):
                        link.insert_before(' ')
                    # Добавляем пробел после ссылки если его нет  
                    if link.next_sibling and not str(link.next_sibling).startswith(' '):
                        link.insert_after(' ')
            
            # Добавляем пробелы перед другими важными элементами
            for elem in element_copy.find_all(['span', 'div']):
                if elem.get_text(strip=True) and elem.parent == element_copy:
                    if elem.previous_sibling and not str(elem.previous_sibling).endswith(' '):
                        elem.insert_before(' ')
                    if elem.next_sibling and not str(elem.next_sibling).startswith(' '):
                        elem.insert_after(' ')
            
            # Извлекаем текст с разделителями
            text = element_copy.get_text(separator=' ', strip=True)
            
            # Заменяем множественные пробелы на одинарные
            text = re.sub(r'\s+', ' ', text)
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения чистого текста: {e}")
            # Fallback к стандартному методу
            return element.get_text(strip=True)
    
    def extract_contracts_from_text(self, text):
        """
        ЕДИНАЯ ФУНКЦИЯ для извлечения Solana контрактов и Ethereum адресов из текста твита
        Возвращает список уникальных контрактов и адресов
        """
        if not text:
            return []
        
        all_contracts = []
        
        # 1. Ищем Ethereum адреса (0x + 40 hex символов)
        eth_addresses = re.findall(r'\b0x[A-Fa-f0-9]{40}\b', text)
        all_contracts.extend(eth_addresses)
        
        # 2. Ищем Solana адреса (32-44 символа, буквы и цифры)
        solana_contracts = re.findall(r'\b[A-Za-z0-9]{32,44}\b', text)
        all_contracts.extend(solana_contracts)
        
        # Очищаем и фильтруем контракты
        clean_contracts = []
        for contract in all_contracts:
            # Убираем "pump" с конца если есть (только для Solana)
            clean_contract = contract
            if contract.endswith('pump') and not contract.startswith('0x'):
                clean_contract = contract[:-4]
            
            # Проверяем тип адреса
            is_eth_address = clean_contract.startswith('0x') and len(clean_contract) == 42 and re.match(r'0x[A-Fa-f0-9]{40}', clean_contract)
            is_solana_address = 32 <= len(clean_contract) <= 44 and clean_contract.isalnum() and not clean_contract.startswith('0x')
            
            if is_eth_address:
                # Ethereum адрес - добавляем если не нулевой
                if not clean_contract.lower() in ['0x0000000000000000000000000000000000000000']:
                    clean_contracts.append(clean_contract)
            elif is_solana_address:
                # Solana адрес - применяем существующую логику
                clean_contracts.append(clean_contract)
        
        # Возвращаем уникальные контракты
        return list(set(clean_contracts))
    
    def extract_profile_data(self, html_content):
        """Извлекает данные профиля из HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Инициализируем данные профиля
            profile_data = {
                'username': None,
                'display_name': None,
                'bio': None,
                'website': None,
                'join_date': None,
                'is_verified': False,
                'avatar_url': None,
                'tweets_count': 0,
                'following_count': 0,
                'followers_count': 0,
                'likes_count': 0
            }
            
            # Ищем блок профиля
            profile_card = soup.find('div', class_='profile-card')
            if not profile_card:
                # Проверяем на блокировку Nitter
                if "Making sure you're not a bot!" in html_content:
                    logger.warning("⚠️ Nitter заблокирован - требуется обновление cookies")
                else:
                    logger.warning("⚠️ Блок profile-card не найден")
                return None
            
            # Извлекаем имя пользователя и отображаемое имя
            username_elem = profile_card.find('a', class_='profile-card-username')
            if username_elem:
                username_text = username_elem.get_text(strip=True)
                if username_text:
                    profile_data['username'] = username_text.replace('@', '')
                else:
                    logger.warning("⚠️ Пустое имя пользователя")
            
            fullname_elem = profile_card.find('a', class_='profile-card-fullname')
            if fullname_elem:
                # Получаем текст без иконок верификации
                display_name = fullname_elem.get_text(strip=True)
                if display_name:
                    profile_data['display_name'] = display_name
                
                # Проверяем верификацию
                verified_icon = fullname_elem.find('span', class_='verified-icon')
                profile_data['is_verified'] = verified_icon is not None
            
            # Извлекаем аватар
            avatar_elem = profile_card.find('img')
            if avatar_elem and avatar_elem.get('src'):
                profile_data['avatar_url'] = avatar_elem['src']
            
            # Извлекаем био
            bio_elem = profile_card.find('div', class_='profile-bio')
            if bio_elem:
                profile_data['bio'] = bio_elem.get_text(strip=True)
            
            # Извлекаем веб-сайт
            website_elem = profile_card.find('div', class_='profile-website')
            if website_elem:
                website_link = website_elem.find('a')
                if website_link:
                    profile_data['website'] = website_link.get('href') or website_link.get_text(strip=True)
            
            # Извлекаем дату регистрации
            joindate_elem = profile_card.find('div', class_='profile-joindate')
            if joindate_elem:
                profile_data['join_date'] = joindate_elem.get_text(strip=True).replace('Joined ', '')
            
            # Извлекаем статистику
            stat_list = profile_card.find('ul', class_='profile-statlist')
            if stat_list:
                stats = stat_list.find_all('li')
                
                for stat in stats:
                    header = stat.find('span', class_='profile-stat-header')
                    number = stat.find('span', class_='profile-stat-num')
                    
                    if header and number:
                        header_text = header.get_text(strip=True).lower()
                        number_text = number.get_text(strip=True)
                        parsed_number = self.parse_number(number_text)
                        
                        if 'tweets' in header_text or 'posts' in header_text:
                            profile_data['tweets_count'] = parsed_number
                        elif 'following' in header_text:
                            profile_data['following_count'] = parsed_number
                        elif 'followers' in header_text:
                            profile_data['followers_count'] = parsed_number
                        elif 'likes' in header_text:
                            profile_data['likes_count'] = parsed_number
            
            username = profile_data.get('username', 'Unknown')
            logger.info(f"📊 Извлечены данные профиля @{username}: "
                       f"{profile_data['followers_count']} подписчиков, "
                       f"{profile_data['tweets_count']} твитов")
            
            return profile_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга профиля: {e}")
            return None
    
    async def get_profile(self, username):
        """Получает данные профиля пользователя с динамической системой куки и Anubis handler"""
        try:
            # Убираем @ если есть
            username = username.replace('@', '')
            
            # Проверяем что session инициализирована
            if not self.session:
                logger.error(f"❌ Session не инициализирована для @{username}")
                return None
            
            # Получаем динамические cookies через новую систему
            proxy, cookies_string = await get_background_proxy_cookie_async(self.session)
            
            # Для IP-адресов Nitter cookies не нужны (пустая строка - это нормально)
            if cookies_string is None:
                logger.error(f"❌ Не удалось получить cookies для @{username}")
                return None
                
            logger.info(f"🔍 Загружаем профиль @{username} (прокси: {'✅' if proxy else '❌'})")
            
            # Парсим строку cookies в словарь для aiohttp
            cookies = {}
            try:
                for cookie_part in cookies_string.split(';'):
                    if '=' in cookie_part:
                        key, value = cookie_part.strip().split('=', 1)
                        cookies[key] = value
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга cookies для @{username}: {e}")
                return None
            
            # Используем динамический выбор домена
            try:
                from duplicate_groups_manager import get_nitter_domain_and_url, add_host_header_if_needed
                current_domain, nitter_base = get_nitter_domain_and_url()
            except ImportError:
                current_domain = "185.207.1.206:8085"
                nitter_base = "http://185.207.1.206:8085"
            url = f"{nitter_base}/{username}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Добавляем заголовок Host для специальных IP-адресов
            add_host_header_if_needed(headers, current_domain)
            
            async with self.session.get(url, headers=headers, cookies=cookies) as response:
                html_content = await response.text()
                
                # 🔍 ПРОВЕРЯЕМ НА ANUBIS CHALLENGE
                if ('id="anubis_challenge"' in html_content or "Making sure you're not a bot!" in html_content):
                    logger.warning(f"🚫 Обнаружен Anubis challenge для @{username} - автоматически решаем...")
                    
                    try:
                        # Автоматически решаем challenge
                        new_cookies = await handle_anubis_challenge_for_session(
                            self.session, url, html_content, force_fresh_challenge=True
                        )
                        
                        if new_cookies:
                            logger.info(f"✅ Challenge решен для @{username}, повторяем запрос...")
                            
                            # Обновляем cookies и повторяем запрос
                            for key, value in new_cookies.items():
                                cookies[key] = value
                                
                            async with self.session.get(url, headers=headers, cookies=cookies) as retry_response:
                                if retry_response.status == 200:
                                    html_content = await retry_response.text()
                                    profile_data = self.extract_profile_data(html_content)
                                    
                                    if profile_data and profile_data.get('username'):
                                        logger.info(f"✅ Профиль @{username} успешно загружен после решения challenge")
                                        return profile_data
                                    else:
                                        logger.warning(f"⚠️ Не удалось извлечь данные профиля @{username} после challenge")
                                        return None
                                else:
                                    logger.warning(f"⚠️ Ошибка после challenge @{username}: {retry_response.status}")
                                    return None
                        else:
                            logger.error(f"❌ Не удалось решить challenge для @{username}")
                            return None
                            
                    except Exception as challenge_error:
                        logger.error(f"❌ Ошибка решения challenge для @{username}: {challenge_error}")
                        return None
                
                elif response.status == 200:
                    profile_data = self.extract_profile_data(html_content)
                    
                    if profile_data and profile_data.get('username'):
                        return profile_data
                    else:
                        logger.warning(f"⚠️ Не удалось извлечь данные профиля @{username}")
                        return None
                        
                elif response.status == 429:
                    logger.warning(f"⚠️ Rate limit при загрузке профиля @{username}")
                    
                    # При 429 переключаемся на следующий домен Nitter, а не меняем прокси
                    from nitter_domain_rotator import get_next_nitter_domain
                    new_domain = get_next_nitter_domain()
                    logger.warning(f"🌐 HTTP 429 - переключаемся на новый домен: {new_domain}")
                    
                    await asyncio.sleep(2)  # Короткая пауза перед повтором
                    
                    # НИКОГДА НЕ СДАЕМСЯ! Рекурсивно вызываем себя с новым доменом
                    return await self.get_profile(username)
                    
                elif response.status == 404:
                    logger.warning(f"⚠️ Профиль @{username} не найден")
                    return None
                    
                else:
                    logger.warning(f"⚠️ Ошибка загрузки профиля @{username}: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения профиля @{username}: {e}")
            return None
    
    def extract_tweets_from_profile(self, html_content):
        """Извлекает твиты с профиля пользователя (исключая ретвиты)"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            tweets = []
            retweets_skipped = 0
            
            # Ищем все твиты в timeline
            timeline_items = soup.find_all('div', class_='timeline-item')
            
            for item in timeline_items:
                # Проверяем наличие retweet-header - если есть, то это ретвит
                retweet_header = item.find('div', class_='retweet-header')
                if retweet_header:
                    retweets_skipped += 1
                    continue  # Пропускаем ретвиты
                
                tweet_content = item.find('div', class_='tweet-content')
                if tweet_content:
                    # Улучшенное извлечение текста с правильными разделителями
                    tweet_text = self.extract_clean_text(tweet_content)
                    if tweet_text:
                        # Извлекаем дату твита
                        tweet_date_elem = item.find('span', class_='tweet-date')
                        
                        # Извлекаем URL твита
                        tweet_link = item.find('a', class_='tweet-link')
                        tweet_url = tweet_link.get('href', '') if tweet_link else ''
                        
                        # Возвращаем словарь вместо строки (для совместимости с duplicate_groups_manager)
                        tweet_dict = {
                            'text': tweet_text,
                            'date': tweet_date_elem,  # Элемент для парсинга в duplicate_groups_manager
                            'url': tweet_url
                        }
                        tweets.append(tweet_dict)
            
            logger.info(f"📱 Извлечено {len(tweets)} оригинальных твитов с профиля (пропущено {retweets_skipped} ретвитов)")
            return tweets
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения твитов: {e}")
            return []
    
    def extract_next_page_url(self, html_content):
        """Извлекает URL следующей страницы из HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Ищем элемент show-more с ссылкой на следующую страницу
            show_more = soup.find('div', class_='show-more')
            if show_more:
                link = show_more.find('a')
                if link and link.get('href'):
                    next_url = link.get('href')
                    logger.debug(f"🔗 Найдена ссылка на следующую страницу: {next_url}")
                    return next_url
            
            logger.debug("📄 Ссылка на следующую страницу не найдена")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения ссылки на следующую страницу: {e}")
            return None
    
    def extract_tweets_with_contracts(self, html_content):
        """Извлекает твиты с профиля и ищет в них контракты (адреса длиной 32-44 символа), исключая ретвиты"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            tweets_with_contracts = []
            retweets_skipped = 0
            
            # Ищем все твиты в timeline
            timeline_items = soup.find_all('div', class_='timeline-item')
            
            for item in timeline_items:
                # Проверяем наличие retweet-header - если есть, то это ретвит
                retweet_header = item.find('div', class_='retweet-header')
                if retweet_header:
                    retweets_skipped += 1
                    continue  # Пропускаем ретвиты
                
                tweet_content = item.find('div', class_='tweet-content')
                if tweet_content:
                    # Улучшенное извлечение текста с правильными разделителями
                    tweet_text = self.extract_clean_text(tweet_content)
                    if tweet_text:
                        # Используем единую функцию для извлечения контрактов
                        contracts = self.extract_contracts_from_text(tweet_text)
                        
                        if contracts:
                            # Также извлекаем дату твита
                            tweet_date = None
                            date_element = item.find('span', class_='tweet-date')
                            if date_element:
                                date_link = date_element.find('a')
                                if date_link:
                                    tweet_date = date_link.get('title', date_link.get_text(strip=True))
                            
                            tweets_with_contracts.append({
                                'text': tweet_text,
                                'contracts': contracts,
                                'date': tweet_date
                            })
            
            logger.info(f"📱 Найдено {len(tweets_with_contracts)} оригинальных твитов с контрактами (пропущено {retweets_skipped} ретвитов)")
            return tweets_with_contracts
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения твитов с контрактами: {e}")
            return []
    
    async def get_profile_with_replies_multi_page(self, username, max_pages=3):
        """
        Получает данные профиля пользователя вместе с твитами из /with_replies 
        с поддержкой пагинации до max_pages страниц
        """
        try:
            # Убираем @ если есть
            username = username.replace('@', '')
            
            # Проверяем что session инициализирована
            if not self.session:
                logger.error(f"❌ Session не инициализирована для @{username}")
                return None, []
            
            # Получаем динамические cookies через новую систему
            proxy, cookies_string = await get_background_proxy_cookie_async(self.session)
            
            # Для IP-адресов Nitter cookies не нужны (пустая строка - это нормально)
            if cookies_string is None:
                logger.error(f"❌ Не удалось получить cookies для @{username}")
                return None, []
            
            # Парсим строку cookies в словарь для aiohttp
            cookies = {}
            try:
                for cookie_part in cookies_string.split(';'):
                    if '=' in cookie_part:
                        key, value = cookie_part.strip().split('=', 1)
                        cookies[key] = value
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга cookies для @{username}: {e}")
                return None, []
            
            # Используем динамический выбор домена
            try:
                from duplicate_groups_manager import get_nitter_domain_and_url, add_host_header_if_needed
                current_domain, nitter_base = get_nitter_domain_and_url()
            except ImportError:
                # Fallback на IP-адрес если не удается импортировать
                current_domain = "185.207.1.206:8085"
                nitter_base = "http://185.207.1.206:8085"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Добавляем заголовок Host для специальных IP-адресов
            add_host_header_if_needed(headers, current_domain)
            
            # Начинаем с первой страницы профиля с /with_replies
            base_url = f"{nitter_base}/{username}/with_replies"
            current_url = base_url
            
            profile_data = None
            all_tweets = []
            all_tweets_with_contracts = []
            page_count = 0
            
            logger.info(f"🔍 Загружаем профиль @{username} с поддержкой replies (до {max_pages} страниц)")
            
            # Проверяем что session инициализирована
            if not self.session:
                logger.error(f"❌ Session не инициализирована для @{username}")
                return None, []
            
            while page_count < max_pages and current_url:
                page_count += 1
                logger.info(f"📄 Загружаем страницу {page_count}/{max_pages} для @{username}")
                
                try:
                    async with self.session.get(current_url, headers=headers, cookies=cookies, timeout=15) as response:
                        if response.status == 200:
                            html_content = await response.text()
                            
                            # 🔍 ПРОВЕРЯЕМ НА ANUBIS CHALLENGE
                            if ('id="anubis_challenge"' in html_content or "Making sure you're not a bot!" in html_content):
                                logger.warning(f"🚫 Обнаружен Anubis challenge для @{username} - автоматически решаем...")
                                
                                try:
                                    # Автоматически решаем challenge
                                    new_cookies = await handle_anubis_challenge_for_session(
                                        self.session, current_url, html_content, force_fresh_challenge=True
                                    )
                                    
                                    if new_cookies:
                                        logger.info(f"✅ Challenge решен для @{username}, обновляем cookies...")
                                        # Обновляем cookies для дальнейших запросов
                                        for key, value in new_cookies.items():
                                            cookies[key] = value
                                        # Повторяем текущий запрос с новыми cookies
                                        continue
                                    else:
                                        logger.error(f"❌ Не удалось решить challenge для @{username}")
                                        break
                                        
                                except Exception as challenge_error:
                                    logger.error(f"❌ Ошибка решения challenge для @{username}: {challenge_error}")
                                    break
                            
                            # Извлекаем данные профиля только с первой страницы
                            if page_count == 1:
                                profile_data = self.extract_profile_data(html_content)
                                if not profile_data:
                                    logger.warning(f"⚠️ Не удалось извлечь данные профиля @{username}")
                                    break
                            
                            # Извлекаем твиты с текущей страницы
                            page_tweets = self.extract_tweets_from_profile(html_content)
                            page_tweets_with_contracts = self.extract_tweets_with_contracts(html_content)
                            
                            all_tweets.extend(page_tweets)
                            all_tweets_with_contracts.extend(page_tweets_with_contracts)
                            
                            logger.info(f"📱 Страница {page_count}: найдено {len(page_tweets)} твитов, {len(page_tweets_with_contracts)} с контрактами")
                            
                            # Ищем ссылку на следующую страницу
                            next_page_path = self.extract_next_page_url(html_content)
                            if next_page_path and page_count < max_pages:
                                # Формируем полный URL для следующей страницы
                                if next_page_path.startswith('?'):
                                    current_url = f"{base_url}{next_page_path}"
                                else:
                                    current_url = f"{nitter_base}{next_page_path}"
                                
                                logger.debug(f"🔗 Следующая страница: {current_url}")
                                
                                # Увеличенная пауза между страницами
                                await asyncio.sleep(3)
                            else:
                                logger.info(f"📄 Больше страниц нет или достигнут лимит для @{username}")
                                break
                                
                        elif response.status == 429:
                            logger.warning(f"⚠️ Rate limit при загрузке страницы {page_count} для @{username}")
                            
                            # При 429 переключаемся на следующий домен Nitter, а не меняем прокси
                            from nitter_domain_rotator import get_next_nitter_domain
                            new_domain = get_next_nitter_domain()
                            logger.warning(f"🌐 HTTP 429 - переключаемся на новый домен: {new_domain}")
                            
                            # Формируем новый URL с новым доменом
                            from urllib.parse import urlparse
                            parsed_url = urlparse(current_url)
                            new_base_url = f"http://{new_domain}" if new_domain.count('.') >= 3 else f"https://{new_domain}"
                            current_url = f"{new_base_url}{parsed_url.path}"
                            if parsed_url.query:
                                current_url += f"?{parsed_url.query}"
                                
                            await asyncio.sleep(2)  # Короткая пауза перед повтором
                            page_count -= 1  # Повторяем ту же страницу с новым доменом
                            continue
                            
                        elif response.status == 404:
                            logger.warning(f"⚠️ Профиль @{username} не найден")
                            break
                            
                        else:
                            logger.warning(f"⚠️ Ошибка загрузки страницы {page_count} для @{username}: {response.status}")
                            break
                            
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ Таймаут при загрузке страницы {page_count} для @{username}")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки страницы {page_count} для @{username}: {e}")
                    break
            
            # Подводим итоги
            total_tweets = len(all_tweets)
            total_contracts = len(all_tweets_with_contracts)
            
            if profile_data:
                # Добавляем информацию о найденных твитах в данные профиля
                profile_data['total_loaded_tweets'] = total_tweets
                profile_data['tweets_with_contracts'] = total_contracts
                profile_data['pages_loaded'] = page_count
                
                logger.info(f"✅ @{username}: профиль загружен, {page_count} страниц, {total_tweets} твитов, {total_contracts} с контрактами")
                return profile_data, all_tweets, all_tweets_with_contracts
            else:
                logger.warning(f"⚠️ Не удалось загрузить профиль @{username}")
                return None, all_tweets, all_tweets_with_contracts
                
        except Exception as e:
            logger.error(f"❌ Общая ошибка загрузки профиля с replies @{username}: {e}")
            return None, [], []

    async def get_profile_with_tweets(self, username, retry_count=0, max_retries=3):
        """Получает данные профиля пользователя вместе с твитами с механизмом повторных попыток"""
        try:
            # Убираем @ если есть
            username = username.replace('@', '')
            
            # Проверяем что session инициализирована
            if not self.session:
                logger.error(f"❌ Session не инициализирована для @{username}")
                return None, []
            
            # Получаем динамические cookies через новую систему
            proxy, cookies_string = await get_background_proxy_cookie_async(self.session)
            
            # Для IP-адресов Nitter cookies не нужны (пустая строка - это нормально)
            if cookies_string is None:
                logger.error(f"❌ Не удалось получить cookies для @{username}")
                return None, []
            
            # Парсим строку cookies в словарь для aiohttp
            cookies = {}
            try:
                for cookie_part in cookies_string.split(';'):
                    if '=' in cookie_part:
                        key, value = cookie_part.strip().split('=', 1)
                        cookies[key] = value
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга cookies для @{username}: {e}")
                return None, []
            
            # Используем динамический выбор домена
            try:
                from duplicate_groups_manager import get_nitter_domain_and_url, add_host_header_if_needed
                current_domain, nitter_base = get_nitter_domain_and_url()
            except ImportError:
                current_domain = "185.207.1.206:8085"
                nitter_base = "http://185.207.1.206:8085"
            url = f"{nitter_base}/{username}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Добавляем заголовок Host для специальных IP-адресов
            add_host_header_if_needed(headers, current_domain)
            
            if retry_count == 0:
                logger.info(f"🔍 Загружаем профиль с твитами @{username}")
            else:
                logger.warning(f"🔄 Повторная попытка {retry_count}/{max_retries} загрузки профиля @{username}")
            
            # Проверяем что session инициализирована
            if not self.session:
                logger.error(f"❌ Session не инициализирована для @{username}")
                return None, []
            
            async with self.session.get(url, headers=headers, cookies=cookies) as response:
                if response.status == 200:
                    html_content = await response.text()
                    
                    # Извлекаем данные профиля
                    profile_data = self.extract_profile_data(html_content)
                    
                    # Извлекаем твиты
                    tweets = self.extract_tweets_from_profile(html_content)
                    
                    if profile_data and profile_data.get('username'):
                        return profile_data, tweets
                    else:
                        logger.warning(f"⚠️ Не удалось извлечь данные профиля @{username}")
                        return None, tweets
                        
                elif response.status == 429:
                    logger.warning(f"⚠️ Rate limit при загрузке профиля @{username}")
                    
                    # При 429 переключаемся на следующий домен Nitter, а не меняем прокси
                    from nitter_domain_rotator import get_next_nitter_domain
                    new_domain = get_next_nitter_domain()
                    logger.warning(f"🌐 HTTP 429 - переключаемся на новый домен: {new_domain}")
                    
                    await asyncio.sleep(2)  # Короткая пауза перед повтором
                    
                    # НИКОГДА НЕ СДАЕМСЯ! Рекурсивно вызываем себя с новым доменом
                    return await self.get_profile_with_tweets(username, retry_count, max_retries)
                    
                elif response.status == 404:
                    logger.warning(f"⚠️ Профиль @{username} не найден")
                    return None, []
                    
                else:
                    logger.warning(f"⚠️ Ошибка загрузки профиля @{username}: {response.status}")
                    return None, []
                    
        except Exception as e:
            # Проверяем на сетевые ошибки
            is_network_error = (
                "Cannot connect to host" in str(e) or
                "Network is unreachable" in str(e) or
                "Connection timeout" in str(e) or
                "TimeoutError" in str(e) or
                "ClientConnectorError" in str(e)
            )
            
            if is_network_error and retry_count < max_retries:
                retry_delay = 2 + retry_count  # Увеличиваем задержку с каждой попыткой
                logger.warning(f"🌐 Сетевая ошибка для @{username}: {e}")
                logger.info(f"🔄 Повторная попытка через {retry_delay}с (попытка {retry_count + 1}/{max_retries})")
                await asyncio.sleep(retry_delay)
                return await self.get_profile_with_tweets(username, retry_count + 1, max_retries)
            else:
                logger.error(f"❌ Ошибка получения профиля с твитами @{username}: {e}")
                return None, []

    async def get_multiple_profiles(self, usernames, delay=1.0):
        """Получает профили нескольких пользователей"""
        profiles = {}
        
        for i, username in enumerate(usernames, 1):
            logger.info(f"📈 Загрузка профиля {i}/{len(usernames)}: @{username}")
            
            try:
                profile_data = await self.get_profile(username)
                if profile_data and profile_data.get('username'):
                    profiles[username] = profile_data
                else:
                    logger.warning(f"⚠️ Пустые данные для профиля @{username}")
                    profiles[username] = None
            except Exception as e:
                logger.error(f"❌ Ошибка получения профиля @{username}: {e}")
                profiles[username] = None
            
            # Увеличенная пауза между запросами профилей
            if i < len(usernames):
                await asyncio.sleep(max(delay, 3.0))
        
        logger.info(f"✅ Загружено {len([p for p in profiles.values() if p])} из {len(usernames)} профилей")
        return profiles

    async def analyze_author_contracts_advanced(self, username, max_pages=3):
        """
        Анализирует контракты у автора Twitter с поддержкой /with_replies и пагинации
        Возвращает детальную информацию о найденных контрактах
        """
        try:
            profile_data, all_tweets, tweets_with_contracts = await self.get_profile_with_replies_multi_page(username, max_pages)
            
            if not profile_data:
                return {
                    'success': False,
                    'error': 'Не удалось загрузить профиль',
                    'total_tweets': 0,
                    'tweets_with_contracts': 0,
                    'unique_contracts': 0,
                    'contracts_analysis': {}
                }
            
            # Анализируем найденные контракты
            all_contracts = []
            contract_frequency = {}
            
            for tweet in tweets_with_contracts:
                # Проверяем что tweet это словарь
                if not isinstance(tweet, dict):
                    logger.debug(f"⚠️ Пропущен твит неправильного типа в анализе контрактов: {type(tweet)}")
                    continue
                    
                contracts = tweet.get('contracts', [])
                if not isinstance(contracts, list):
                    logger.debug(f"⚠️ Поле contracts не является списком: {type(contracts)}")
                    continue
                    
                for contract in contracts:
                    if isinstance(contract, str) and 32 <= len(contract) <= 44 and contract.isalnum():
                        all_contracts.append(contract)
                        contract_frequency[contract] = contract_frequency.get(contract, 0) + 1
            
            unique_contracts = len(set(all_contracts))
            total_contract_mentions = len(all_contracts)
            
            # Вычисляем статистики
            if len(tweets_with_contracts) > 0:
                contract_diversity_percent = (unique_contracts / len(tweets_with_contracts)) * 100
                
                # Находим самый часто упоминаемый контракт
                if contract_frequency:
                    most_frequent_contract = max(contract_frequency.items(), key=lambda x: x[1])
                    max_contract_concentration = (most_frequent_contract[1] / total_contract_mentions) * 100
                else:
                    most_frequent_contract = None
                    max_contract_concentration = 0
            else:
                contract_diversity_percent = 0
                most_frequent_contract = None
                max_contract_concentration = 0
            
            # Топ-5 самых упоминаемых контрактов
            top_contracts = sorted(contract_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Анализ качества с адаптивными порогами
            total_tweets_analyzed = len(all_tweets)
            
            if unique_contracts == 0:
                quality_analysis = "Нет контрактов"
                spam_likelihood = "Неизвестно"
            elif max_contract_concentration >= 80:
                quality_analysis = "Отличная концентрация"
                spam_likelihood = "Низкая"
            elif max_contract_concentration >= 60:
                quality_analysis = "Хорошая концентрация"
                spam_likelihood = "Низкая"
            elif max_contract_concentration >= 40:
                quality_analysis = "Умеренная концентрация"
                spam_likelihood = "Средняя"
            else:
                # АДАПТИВНЫЕ ПОРОГИ в зависимости от количества твитов
                diversity_threshold = 40  # По умолчанию для больших выборок
                
                if total_tweets_analyzed < 10:
                    diversity_threshold = 50  # Мягкий порог для малых выборок
                elif total_tweets_analyzed < 20:
                    diversity_threshold = 30  # Умеренный порог для средних выборок
                else:
                    diversity_threshold = 40  # Умеренный порог для больших выборок
                
                if contract_diversity_percent >= diversity_threshold:
                    quality_analysis = f"Слишком высокое разнообразие (>{diversity_threshold}% для {total_tweets_analyzed} твитов)"
                    spam_likelihood = "Очень высокая"
                else:
                    quality_analysis = f"Приемлемое разнообразие (<{diversity_threshold}% для {total_tweets_analyzed} твитов)"
                    spam_likelihood = "Низкая"
            
            result = {
                'success': True,
                'profile_data': profile_data,
                'total_tweets_loaded': len(all_tweets),
                'tweets_with_contracts': len(tweets_with_contracts),
                'unique_contracts': unique_contracts,
                'total_contract_mentions': total_contract_mentions,
                'contract_diversity_percent': round(contract_diversity_percent, 1),
                'max_contract_concentration_percent': round(max_contract_concentration, 1),
                'most_frequent_contract': most_frequent_contract,
                'top_contracts': top_contracts,
                'quality_analysis': quality_analysis,
                'spam_likelihood': spam_likelihood,
                'pages_analyzed': profile_data.get('pages_loaded', 0),
                'contracts_details': tweets_with_contracts
            }
            
            logger.info(f"📊 Анализ @{username}: {unique_contracts} уник. контрактов из {total_contract_mentions} упоминаний, {quality_analysis}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа контрактов автора @{username}: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_tweets': 0,
                'tweets_with_contracts': 0,
                'unique_contracts': 0,
                'contracts_analysis': {}
            }

async def test_profile_parser():
    """Тестирование парсера профилей"""
    logger.info("🧪 Тестирование парсера профилей Twitter")
    
    test_usernames = ['LaunchOnPump', 'elonmusk', 'pumpdotfun']
    
    async with TwitterProfileParser() as parser:
        profiles = await parser.get_multiple_profiles(test_usernames)
        
        for username, profile in profiles.items():
            if profile:
                logger.info(f"📊 Профиль @{username}:")
                logger.info(f"  • Отображаемое имя: {profile.get('display_name', 'N/A')}")
                logger.info(f"  • Подписчики: {profile.get('followers_count', 0):,}")
                logger.info(f"  • Твиты: {profile.get('tweets_count', 0):,}")
                logger.info(f"  • Верифицирован: {profile.get('is_verified', False)}")
                logger.info(f"  • Дата регистрации: {profile.get('join_date', 'N/A')}")
            else:
                logger.info(f"❌ Профиль @{username}: не удалось загрузить")

async def test_profile_with_replies():
    """Тестирование нового парсера профилей с replies и пагинацией"""
    logger.info("🧪 Тестирование парсера профилей Twitter с /with_replies и пагинацией")
    
    test_username = 'Tsomisol'  # Пример из запроса
    
    async with TwitterProfileParser() as parser:
        profile_data, all_tweets, tweets_with_contracts = await parser.get_profile_with_replies_multi_page(test_username, max_pages=3)
        
        if profile_data:
            logger.info(f"📊 Результаты для @{test_username}:")
            logger.info(f"  • Отображаемое имя: {profile_data.get('display_name', 'N/A')}")
            logger.info(f"  • Подписчики: {profile_data.get('followers_count', 0):,}")
            logger.info(f"  • Твиты на профиле: {profile_data.get('tweets_count', 0):,}")
            logger.info(f"  • Верифицирован: {profile_data.get('is_verified', False)}")
            logger.info(f"  • Загружено страниц: {profile_data.get('pages_loaded', 0)}")
            logger.info(f"  • Загружено твитов: {profile_data.get('total_loaded_tweets', 0)}")
            logger.info(f"  • Твитов с контрактами: {profile_data.get('tweets_with_contracts', 0)}")
            
            # Показываем примеры твитов с контрактами
            if tweets_with_contracts:
                logger.info(f"\n📝 Примеры твитов с контрактами:")
                for i, tweet in enumerate(tweets_with_contracts[:3], 1):
                    # Проверяем что tweet это словарь
                    if isinstance(tweet, dict):
                        logger.info(f"  {i}. [{tweet.get('date', 'N/A')}] {tweet.get('text', '')[:100]}...")
                        logger.info(f"     🔗 Контракты: {', '.join(tweet.get('contracts', [])[:2])}")
                    else:
                        logger.info(f"  {i}. Твит неправильного формата (тип: {type(tweet)})")
        else:
            logger.info(f"❌ Профиль @{test_username}: не удалось загрузить")

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    from logger_config import setup_logging
    from dotenv import load_dotenv
    
    load_dotenv()
    setup_logging()
    
    # Проверяем аргументы командной строки для выбора теста
    if len(sys.argv) > 1 and sys.argv[1] == "replies":
        logger.info("🚀 Запуск теста с /with_replies и пагинацией")
        asyncio.run(test_profile_with_replies())
    else:
        logger.info("🚀 Запуск стандартного теста профилей")
        asyncio.run(test_profile_parser()) 