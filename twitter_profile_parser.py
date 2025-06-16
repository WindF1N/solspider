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
from cookie_rotation import BackgroundCookieRotator

logger = logging.getLogger(__name__)

class TwitterProfileParser:
    """Парсер профилей авторов твитов"""
    
    def __init__(self):
        self.session = None
        try:
            self.cookie_rotator = BackgroundCookieRotator()
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации cookie_rotator: {e}")
            self.cookie_rotator = None
        
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
        """Получает данные профиля пользователя"""
        try:
            # Убираем @ если есть
            username = username.replace('@', '')
            
            # Получаем актуальные cookies
            if not self.cookie_rotator:
                logger.error(f"❌ Cookie rotator не инициализирован для @{username}")
                return None
                
            cookies_string = self.cookie_rotator.get_next_cookie()
            
            # Проверяем что cookies_string не None
            if not cookies_string:
                logger.error(f"❌ Не удалось получить cookies для @{username}")
                return None
            
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
            
            url = f"https://nitter.tiekoetter.com/{username}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            logger.info(f"🔍 Загружаем профиль @{username}")
            
            # Проверяем что session инициализирована
            if not self.session:
                logger.error(f"❌ Session не инициализирована для @{username}")
                return None
            
            async with self.session.get(url, headers=headers, cookies=cookies) as response:
                if response.status == 200:
                    html_content = await response.text()
                    profile_data = self.extract_profile_data(html_content)
                    
                    if profile_data and profile_data.get('username'):
                        return profile_data
                    else:
                        logger.warning(f"⚠️ Не удалось извлечь данные профиля @{username}")
                        return None
                        
                elif response.status == 429:
                    logger.warning(f"⚠️ Rate limit при загрузке профиля @{username}")
                    # Помечаем текущий cookie как заблокированный
                    try:
                        if hasattr(self.cookie_rotator, 'mark_cookie_failed'):
                            self.cookie_rotator.mark_cookie_failed(cookies_string)
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка при отметке cookie как неудачный: {e}")
                    await asyncio.sleep(2)
                    return None
                    
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
        """Извлекает твиты с профиля пользователя"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            tweets = []
            
            # Ищем все твиты в timeline
            timeline_items = soup.find_all('div', class_='timeline-item')
            
            for item in timeline_items:
                tweet_content = item.find('div', class_='tweet-content')
                if tweet_content:
                    tweet_text = tweet_content.get_text(strip=True)
                    if tweet_text:
                        tweets.append(tweet_text)
            
            logger.info(f"📱 Извлечено {len(tweets)} твитов с профиля")
            return tweets
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения твитов: {e}")
            return []
    
    async def get_profile_with_tweets(self, username):
        """Получает данные профиля пользователя вместе с твитами"""
        try:
            # Убираем @ если есть
            username = username.replace('@', '')
            
            # Получаем актуальные cookies
            if not self.cookie_rotator:
                logger.error(f"❌ Cookie rotator не инициализирован для @{username}")
                return None, []
                
            cookies_string = self.cookie_rotator.get_next_cookie()
            
            # Проверяем что cookies_string не None
            if not cookies_string:
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
            
            url = f"https://nitter.tiekoetter.com/{username}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            logger.info(f"🔍 Загружаем профиль с твитами @{username}")
            
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
                    # Помечаем текущий cookie как заблокированный
                    try:
                        if hasattr(self.cookie_rotator, 'mark_cookie_failed'):
                            self.cookie_rotator.mark_cookie_failed(cookies_string)
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка при отметке cookie как неудачный: {e}")
                    await asyncio.sleep(2)
                    return None, []
                    
                elif response.status == 404:
                    logger.warning(f"⚠️ Профиль @{username} не найден")
                    return None, []
                    
                else:
                    logger.warning(f"⚠️ Ошибка загрузки профиля @{username}: {response.status}")
                    return None, []
                    
        except Exception as e:
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
            
            # Пауза между запросами
            if i < len(usernames):
                await asyncio.sleep(delay)
        
        logger.info(f"✅ Загружено {len([p for p in profiles.values() if p])} из {len(usernames)} профилей")
        return profiles

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

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    from logger_config import setup_logging
    from dotenv import load_dotenv
    
    load_dotenv()
    setup_logging()
    
    asyncio.run(test_profile_parser()) 