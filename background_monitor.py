#!/usr/bin/env python3
"""
Фоновый мониторинг токенов для отслеживания появления адресов контрактов в Twitter
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from database import get_db_manager, Token
from pump_bot import search_single_query, send_telegram, extract_tweet_authors, TWITTER_AUTHOR_BLACKLIST
from cookie_rotation import background_cookie_rotator
from logger_config import setup_logging
from twitter_profile_parser import TwitterProfileParser
import re
import aiohttp
from bs4 import BeautifulSoup

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

class BackgroundTokenMonitor:
    """Фоновый мониторинг токенов"""
    
    def __init__(self):
        self.db_manager = get_db_manager()
        self.running = False
        self.max_token_age_hours = 1  # Мониторим токены не старше 1 часа
        self.batch_delay = 0  # Задержка между батчами 10 секунд
        # Парсер профилей Twitter (будет создан в async функциях)
        
        # Базовые заголовки для Nitter запросов (cookie будет добавлен автоматически)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def get_tokens_to_monitor(self):
        """Получает токены для мониторинга (продолжает мониторить даже найденные)"""
        session = self.db_manager.Session()
        try:
            # Токены созданные не более 1 часа назад (убираем фильтр по twitter_contract_tweets)
            cutoff_time = datetime.utcnow() - timedelta(hours=self.max_token_age_hours)
            
            tokens = session.query(Token).filter(
                Token.created_at >= cutoff_time,           # Не старше 1 часа
                # УБРАЛИ ФИЛЬТР: Token.twitter_contract_tweets == 0,  # Теперь мониторим ВСЕ токены
                Token.mint.isnot(None),                    # Есть адрес контракта
                Token.symbol.isnot(None)                   # Есть символ
            ).order_by(Token.created_at.desc()).all()
            
            # Разделяем токены на новые и уже найденные для статистики
            new_tokens = [t for t in tokens if t.twitter_contract_tweets == 0]
            found_tokens = [t for t in tokens if t.twitter_contract_tweets > 0]
            
            logger.info(f"📊 Мониторинг: {len(new_tokens)} новых + {len(found_tokens)} найденных = {len(tokens)} токенов")
            return tokens
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения токенов для мониторинга: {e}")
            return []
        finally:
            session.close()
    
    async def check_contract_mentions(self, token, cycle_cookie):
        """Проверяет появление НОВЫХ упоминаний контракта в Twitter с парсингом авторов"""
        try:
            # Получаем данные с авторами
            tweets_count, engagement, authors = await self.get_contract_mentions_with_authors(token, cycle_cookie)
            
            # Проверяем если возвращается 0,0 - возможно блокировка
            if tweets_count == 0 and engagement == 0:
                logger.debug(f"🔍 Контракт {token.symbol} не найден в Twitter (или блокировка)")
                return False
            
            # Сравниваем с предыдущими данными
            previous_tweets = token.twitter_contract_tweets or 0
            new_tweets_found = tweets_count - previous_tweets
            
            if new_tweets_found > 0:
                logger.info(f"🎯 НОВЫЕ твиты для {token.symbol}! Было: {previous_tweets}, стало: {tweets_count} (+{new_tweets_found}), авторов: {len(authors)}")
                
                # Обновляем данные в БД
                session = self.db_manager.Session()
                try:
                    db_token = session.query(Token).filter_by(id=token.id).first()
                    if db_token:
                        db_token.twitter_contract_tweets = tweets_count
                        db_token.twitter_contract_found = True
                        db_token.updated_at = datetime.utcnow()
                        session.commit()
                        
                        logger.info(f"✅ Обновлена БД для токена {token.symbol}: {previous_tweets} → {tweets_count}")
                        
                        # Отправляем уведомление только о НОВЫХ твитах
                        is_first_discovery = previous_tweets == 0
                        await self.send_contract_alert(token, tweets_count, engagement, authors, is_first_discovery)
                        
                except Exception as e:
                    session.rollback()
                    logger.error(f"❌ Ошибка обновления БД для {token.symbol}: {e}")
                finally:
                    session.close()
                    
                return True
            elif tweets_count == previous_tweets and tweets_count > 0:
                logger.debug(f"🔍 {token.symbol}: количество твитов не изменилось ({tweets_count})")
                return False
            else:
                logger.debug(f"🔍 Контракт {token.symbol} пока не найден в Twitter")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки контракта {token.symbol}: {e}")
            return False
    
    async def send_contract_alert(self, token, tweets_count, engagement, authors, is_first_discovery=True):
        """Отправляет уведомление о найденном контракте в Twitter"""
        try:
            emoji = "🔥" if is_first_discovery else "🚨"
            title = "КОНТРАКТ НАЙДЕН В TWITTER!" if is_first_discovery else f"НОВАЯ АКТИВНОСТЬ ПО КОНТРАКТУ! +{tweets_count - (token.twitter_contract_tweets or 0)} новых твитов!"
            
            message = (
                f"{emoji} <b>{title}</b>\n\n"
                f"🪙 <b>Токен:</b> {token.symbol or 'Unknown'}\n"
                f"💰 <b>Название:</b> {token.name or 'N/A'}\n"
                f"📄 <b>Контракт:</b> <code>{token.mint}</code>\n"
            )
            
            # Добавляем информацию о твитах
            if is_first_discovery:
                action_text = f"📱 <b>Твитов с контрактом:</b> {tweets_count}"
            else:
                previous_tweets = token.twitter_contract_tweets or 0
                new_tweets = tweets_count - previous_tweets
                action_text = f"📱 <b>Всего твитов:</b> {tweets_count} (+{new_tweets} новых)"
            
            message += (
                f"\n📊 <b>Активность:</b> {engagement}\n"
                f"📈 <b>Текущий Market Cap:</b> ${token.market_cap:,.0f}\n\n"
                f"{action_text}\n"
                f"📈 <b>Возможен рост интереса к токену</b>\n\n"
            )
            
            # Добавляем информацию об авторах твитов
            if authors:
                total_followers = sum([author.get('followers_count', 0) for author in authors])
                verified_count = sum([1 for author in authors if author.get('is_verified', False)])
                
                message += f"<b>👥 АВТОРЫ ТВИТОВ С КОНТРАКТОМ ({len(authors)} авторов):</b>\n"
                message += f"   📊 Общий охват: {total_followers:,} подписчиков\n"
                if verified_count > 0:
                    message += f"   ✅ Верифицированных: {verified_count}\n"
                message += "\n"
                
                for i, author in enumerate(authors[:3]):  # Показываем максимум 3 авторов
                    username = author.get('username', 'Unknown')
                    display_name = author.get('display_name', username)
                    followers = author.get('followers_count', 0)
                    verified = "✅" if author.get('is_verified', False) else ""
                    tweet_text = author.get('tweet_text', '')[:80] + "..." if len(author.get('tweet_text', '')) > 80 else author.get('tweet_text', '')
                    
                    message += f"{i+1}. <b>@{username}</b> {verified}\n"
                    if display_name != username:
                        message += f"   📝 {display_name}\n"
                    if followers > 0:
                        message += f"   👥 {followers:,} подписчиков\n"
                    message += f"   💬 \"{tweet_text}\"\n"
                message += "\n"
            
            message += f"⚡ <b>Время действовать!</b>"
            
            # Создаем кнопки для уведомления
            keyboard = [
                [
                    {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/meme/{token.bonding_curve_key or token.mint}"},
                    {"text": "⚡ QUICK BUY", "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{token.mint}"}
                ],
                [
                    {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{token.mint}"}
                ],
            ]
            
            send_telegram(message, keyboard)
            logger.info(f"📤 Отправлено уведомление о контракте {token.symbol} в Telegram")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления: {e}")
    
    async def monitor_cycle(self):
        """Один цикл мониторинга"""
        try:
            start_time = time.time()
            
            # Получаем cookie для всего цикла
            cycle_cookie = background_cookie_rotator.get_cycle_cookie()
            logger.info("🔄 Начинаем цикл фонового мониторинга с новым cookie...")
            
            # Получаем токены для проверки
            tokens = self.get_tokens_to_monitor()
            
            if not tokens:
                logger.debug("📭 Нет токенов для мониторинга в данный момент")
                return
            
            # Проверяем токены батчами по 900 штук (чтобы не перегружать Nitter)
            batch_size = 900
            found_contracts = 0
            
            for i in range(0, len(tokens), batch_size):
                batch = tokens[i:i + batch_size]
                logger.info(f"🔍 Проверяем батч {i//batch_size + 1}: токены {i+1}-{min(i+batch_size, len(tokens))}")
                
                # Проверяем батч параллельно с одним cookie для всего цикла
                tasks = [self.check_contract_mentions(token, cycle_cookie) for token in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Подсчитываем найденные контракты
                for result in results:
                    if result is True:
                        found_contracts += 1
                
                # Небольшая пауза между батчами чтобы не перегружать Nitter
                if i + batch_size < len(tokens):
                    await asyncio.sleep(1)
                
            elapsed = time.time() - start_time
            logger.info(f"✅ Цикл мониторинга завершен за {elapsed:.1f}с. Найдено контрактов: {found_contracts}")

            # Пауза между циклами
            # await asyncio.sleep(10)
            
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
    
    async def start_monitoring(self):
        """Запускает непрерывный фоновый мониторинг"""
        self.running = True
        logger.info(f"🚀 Запуск непрерывного фонового мониторинга")
        
        # Отправляем уведомление о запуске
        start_message = (
            f"🤖 <b>НЕПРЕРЫВНЫЙ ФОНОВЫЙ МОНИТОРИНГ ЗАПУЩЕН!</b>\n\n"
            f"🔍 <b>Отслеживаем:</b> все упоминания адресов контрактов в Twitter\n"
            f"⚡ <b>Режим:</b> непрерывный мониторинг каждого нового твита\n"
            f"📊 <b>Мониторим токены:</b> не старше {self.max_token_age_hours} часа\n"
            f"🔄 <b>Ротация:</b> 10 cookies для фонового мониторинга\n"
            f"🚨 <b>Уведомления:</b> каждый новый уникальный твит с контрактом\n"
            f"🎯 <b>Цель:</b> полный охват растущего интереса\n\n"
            f"🚀 <b>Готов ловить каждый момент роста!</b>"
        )
        send_telegram(start_message)
        
        while self.running:
            try:
                await self.monitor_cycle()
                
                # Небольшая пауза только если нет токенов для мониторинга
                # Иначе сразу переходим к следующему циклу
                logger.info(f"⚡ Переход к следующему циклу мониторинга...")
                
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в мониторинге: {e}")
                await asyncio.sleep(30)  # Пауза при ошибке
    
    def stop_monitoring(self):
        """Останавливает мониторинг"""
        self.running = False
        logger.info("🛑 Остановка фонового мониторинга...")

    async def get_contract_mentions_with_authors(self, token, cycle_cookie):
        """Получает HTML ответы для парсинга авторов"""
        try:
            # Делаем запросы с получением HTML
            urls = [
                f"https://nitter.tiekoetter.com/search?f=tweets&q=%22{token.mint}%22&since=&until=&near=",  # С кавычками
                f"https://nitter.tiekoetter.com/search?f=tweets&q={token.mint}&since=&until=&near="  # Без кавычек
            ]
            
            headers_with_cookie = self.headers.copy()
            headers_with_cookie['Cookie'] = cycle_cookie
            
            all_authors = []
            tweets_count = 0
            engagement = 0
            
            for url in urls:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers_with_cookie, timeout=20) as response:
                            if response.status == 200:
                                html = await response.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Проверяем на блокировку
                                title = soup.find('title')
                                if title and 'Making sure you\'re not a bot!' in title.get_text():
                                    logger.error(f"🚫 NITTER ЗАБЛОКИРОВАН! Контракт: {token.mint} куки '{cycle_cookie}'")
                                    continue
                                
                                # Подсчитываем твиты
                                tweets = soup.find_all('div', class_='timeline-item')
                                tweets_count += len(tweets)
                                
                                # Парсим авторов если найдены твиты
                                if tweets:
                                    authors = await extract_tweet_authors(soup, token.mint, True)
                                    all_authors.extend(authors)
                                    
                                    # Подсчитываем активность
                                    for tweet in tweets:
                                        stats = tweet.find_all('span', class_='tweet-stat')
                                        for stat in stats:
                                            icon_container = stat.find('div', class_='icon-container')
                                            if icon_container:
                                                text = icon_container.get_text(strip=True)
                                                numbers = re.findall(r'\d+', text)
                                                if numbers:
                                                    engagement += int(numbers[0])
                                
                except Exception as e:
                    logger.error(f"❌ Ошибка запроса к {url}: {e}")
                    continue
            
            # Убираем дубликаты авторов и проверяем черный список
            unique_authors = []
            seen_usernames = set()
            blacklisted_count = 0
            
            for author in all_authors:
                username = author.get('username', '')
                if username and username not in seen_usernames:
                    # Дополнительная проверка черного списка
                    if username.lower() in TWITTER_AUTHOR_BLACKLIST:
                        logger.info(f"🚫 Автор @{username} из фонового мониторинга исключен (черный список)")
                        blacklisted_count += 1
                        continue
                    
                    unique_authors.append(author)
                    seen_usernames.add(username)
            
            if blacklisted_count > 0:
                logger.info(f"🚫 Исключено {blacklisted_count} авторов из черного списка для токена {token.symbol}")
            
            return tweets_count, engagement, unique_authors
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных для {token.symbol}: {e}")
            return 0, 0, []

async def main():
    """Основная функция для запуска фонового мониторинга"""
    monitor = BackgroundTokenMonitor()
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("🛑 Мониторинг остановлен пользователем")
        monitor.stop_monitoring()
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка мониторинга: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 