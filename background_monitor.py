#!/usr/bin/env python3
"""
Фоновый мониторинг токенов для отслеживания появления адресов контрактов в Twitter
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from database import get_db_manager, Token
from pump_bot import search_single_query, send_telegram, extract_tweet_authors, TWITTER_AUTHOR_BLACKLIST, analyze_author_contract_diversity
from cookie_rotation import background_proxy_cookie_rotator, background_cookie_rotator
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
        self.batch_delay = 0  # Задержка между батчами (адаптивная)
        self.consecutive_errors = 0  # Счетчик последовательных ошибок
        self.batch_mode = False  # Режим пакетной обработки
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
    
    async def check_contract_mentions(self, token, proxy, cycle_cookie):
        """Проверяет появление НОВЫХ упоминаний контракта в Twitter с парсингом авторов"""
        try:
            # Получаем данные с авторами
            tweets_count, engagement, authors = await self.get_contract_mentions_with_authors(token, proxy, cycle_cookie)
            
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
                        
                        # Проверяем качество авторов перед отправкой уведомления
                        should_notify = self.should_notify_based_on_authors(authors)
                        
                        if should_notify:
                            # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: не отправлялось ли уже отложенное уведомление
                            if db_token.notification_sent and previous_tweets == 0:
                                logger.info(f"🚫 Фоновое уведомление для {token.symbol} пропущено - уже было отложенное уведомление")
                            else:
                                # Отправляем уведомление только о НОВЫХ твитах
                                is_first_discovery = previous_tweets == 0
                                await self.send_contract_alert(token, tweets_count, engagement, authors, is_first_discovery)
                        else:
                            logger.info(f"🚫 Уведомление для {token.symbol} заблокировано - все авторы являются спамерами")
                        
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
            # Увеличиваем счетчик ошибок для адаптивного режима
            self.consecutive_errors += 1
            return False
    
    def should_notify_based_on_authors(self, authors):
        """
        Проверяет, стоит ли отправлять уведомление на основе качества авторов
        ИСПРАВЛЕННАЯ ЛОГИКА: фокус на одном контракте = хорошо, много разных = плохо
        """
        if not authors:
            return False  # Нет авторов - не отправляем
        
        excellent_authors = 0  # Вспышки активности (≥80%)
        good_authors = 0       # Хорошие авторы (≥40%)
        new_accounts = 0       # Новые аккаунты (≤2 твитов)
        spam_authors = 0       # Спамеры разных контрактов
        
        for author in authors:
            diversity_percent = author.get('contract_diversity', 0)
            spam_percent = author.get('max_contract_spam', 0)
            total_tweets = author.get('total_contract_tweets', 0)
            username = author.get('username', 'Unknown')
            
            # ПРОВЕРКА НА ОТСУТСТВИЕ ДАННЫХ АНАЛИЗА
            if total_tweets == 0 and spam_percent == 0 and diversity_percent == 0:
                logger.warning(f"⚠️ @{username}: недостаточно данных для анализа ({total_tweets} твитов) - пропускаем")
                continue
            
            # НОВАЯ ЛОГИКА: малое количество твитов = потенциально хороший сигнал
            if total_tweets <= 2:
                new_accounts += 1
                logger.info(f"🆕 @{username}: новый аккаунт ({total_tweets} твитов) - потенциальный сигнал")
                continue
            
            # Анализируем концентрацию на одном контракте
            if spam_percent >= 80:
                excellent_authors += 1
                logger.info(f"🔥 @{username}: ВСПЫШКА! ({spam_percent:.1f}% концентрация на одном контракте)")
            elif spam_percent >= 40:
                good_authors += 1
                logger.info(f"⭐ @{username}: ХОРОШИЙ ({spam_percent:.1f}% концентрация на одном контракте)")
            elif diversity_percent >= 30:
                # Много РАЗНЫХ контрактов = плохо
                spam_authors += 1
                logger.info(f"🚫 @{username}: СПАМЕР РАЗНЫХ ТОКЕНОВ ({diversity_percent:.1f}% разных контрактов)")
            elif spam_percent >= 20:
                # Умеренная концентрация - принимаем
                good_authors += 1
                logger.info(f"🟡 @{username}: умеренная концентрация ({spam_percent:.1f}%) - принимаем")
            else:
                # НИЗКАЯ концентрация И низкое разнообразие = подозрительно
                spam_authors += 1
                logger.info(f"🚫 @{username}: НИЗКОЕ КАЧЕСТВО ({spam_percent:.1f}% концентрация, {diversity_percent:.1f}% разнообразие) - отклоняем")
        
        # СМЯГЧЕННЫЕ КРИТЕРИИ: отправляем если есть хорошие сигналы
        should_notify = excellent_authors > 0 or good_authors > 0 or new_accounts > 0
        
        logger.info(f"📊 ИСПРАВЛЕННЫЙ АНАЛИЗ АВТОРОВ:")
        logger.info(f"   🔥 Вспышки (≥80%): {excellent_authors}")
        logger.info(f"   ⭐ Хорошие (≥40%): {good_authors}")
        logger.info(f"   🆕 Новые аккаунты (≤2 твитов): {new_accounts}")
        logger.info(f"   🚫 Спамеры разных токенов: {spam_authors}")
        logger.info(f"   🎯 РЕШЕНИЕ: {'ОТПРАВИТЬ' if should_notify else 'ЗАБЛОКИРОВАТЬ'}")
        
        if not should_notify:
            logger.info(f"🚫 Уведомление заблокировано - только спамеры разных токенов")
        
        return should_notify

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
                    
                    # Информация о спаме контрактов
                    diversity_percent = author.get('contract_diversity', 0)
                    spam_percent = author.get('max_contract_spam', 0)
                    diversity_recommendation = author.get('diversity_recommendation', 'Нет данных')
                    spam_analysis = author.get('spam_analysis', 'Нет данных')
                    is_spam_likely = author.get('is_spam_likely', False)
                    total_contract_tweets = author.get('total_contract_tweets', 0)
                    unique_contracts = author.get('unique_contracts_count', 0)
                    
                    # Эмодзи для статуса автора (высокая концентрация = хорошо)
                    spam_indicator = ""
                    if spam_percent >= 80:
                        spam_indicator = " 🔥"  # Вспышка активности
                    elif spam_percent >= 60:
                        spam_indicator = " ⭐"  # Высокая концентрация
                    elif spam_percent >= 40:
                        spam_indicator = " 🟡"  # Умеренная концентрация
                    elif is_spam_likely:
                        spam_indicator = " 🚫"  # Много разных контрактов
                    
                    message += f"{i+1}. <b>@{username}</b> {verified}{spam_indicator}\n"
                    if display_name != username:
                        message += f"   📝 {display_name}\n"
                    if followers > 0:
                        message += f"   👥 {followers:,} подписчиков\n"
                    
                    # Показываем анализ концентрации контрактов
                    if total_contract_tweets > 0:
                        message += f"   📊 Контракты: {unique_contracts} из {total_contract_tweets} твитов (концентрация: {spam_percent:.1f}%)\n"
                        message += f"   🎯 Анализ: {spam_analysis}\n"
                    
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
            
            # Получаем связку прокси+cookie для всего цикла
            proxy, cycle_cookie = background_proxy_cookie_rotator.get_cycle_proxy_cookie()
            logger.info("🔄 Начинаем цикл фонового мониторинга с новой связкой прокси+cookie...")
            
            # Получаем токены для проверки
            tokens = self.get_tokens_to_monitor()
            
            if not tokens:
                logger.debug("📭 Нет токенов для мониторинга в данный момент")
                return
            
            # ОПТИМИЗАЦИЯ: увеличенные батчи для повышения производительности
            if self.consecutive_errors > 10:
                batch_size = 15  # Уменьшены батчи при ошибках: 50→15
                self.batch_mode = True
                logger.warning(f"🚨 Активирован режим восстановления: батчи по {batch_size} токенов")
            elif len(tokens) > 20:
                batch_size = 30  # Уменьшен оптимальный размер: 100→30
                self.batch_mode = True
                logger.info(f"⚡ Пакетный режим: батчи по {batch_size} токенов (очередь: {len(tokens)})")
            else:
                batch_size = len(tokens)  # Обрабатываем все сразу
                self.batch_mode = False
            
            found_contracts = 0
            
            for i in range(0, len(tokens), batch_size):
                batch = tokens[i:i + batch_size]
                logger.info(f"🔍 Проверяем батч {i//batch_size + 1}: токены {i+1}-{min(i+batch_size, len(tokens))}")
                
                # Проверяем батч параллельно с одной связкой прокси+cookie для всего цикла
                tasks = [self.check_contract_mentions(token, proxy, cycle_cookie) for token in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Подсчитываем найденные контракты и ошибки
                batch_errors = 0
                for result in results:
                    if result is True:
                        found_contracts += 1
                        # Сбрасываем счетчик ошибок при успехе
                        self.consecutive_errors = max(0, self.consecutive_errors - 1)
                    elif isinstance(result, Exception):
                        batch_errors += 1
                
                # Адаптивные паузы между батчами
                if i + batch_size < len(tokens):
                    if self.batch_mode:
                        # В пакетном режиме - минимальные паузы
                        pause = 0.1 if batch_errors < len(batch) // 2 else 0.5
                    else:
                        # Обычный режим - без пауз
                        pause = 0
                    
                    if pause > 0:
                        await asyncio.sleep(pause)
                
            elapsed = time.time() - start_time
            
            # Логируем статистику производительности
            tokens_per_second = len(tokens) / elapsed if elapsed > 0 else 0
            mode_info = f"[{'ПАКЕТНЫЙ' if self.batch_mode else 'ОБЫЧНЫЙ'} режим]"
            
            logger.info(f"✅ Цикл мониторинга завершен за {elapsed:.1f}с {mode_info}")
            logger.info(f"📊 Производительность: {tokens_per_second:.1f} токенов/сек, найдено: {found_contracts}")
            logger.info(f"🔧 Ошибки подряд: {self.consecutive_errors}")

        except Exception as e:
            logger.error(f"❌ Ошибка в цикле мониторинга: {e}")
            self.consecutive_errors += 1
    
    async def emergency_clear_monitor_overload(self):
        """Экстренная очистка при перегрузке фонового мониторинга"""
        try:
            # Если слишком много последовательных ошибок
            if self.consecutive_errors > 50:  # Больше 50 = критическая ситуация
                logger.warning(f"🚨 КРИТИЧЕСКАЯ ПЕРЕГРУЗКА МОНИТОРИНГА: {self.consecutive_errors} ошибок подряд!")
                
                # Сбрасываем счетчик ошибок наполовину
                self.consecutive_errors = self.consecutive_errors // 2
                
                # Активируем режим восстановления
                self.batch_mode = True
                
                logger.warning(f"🚨 ЭКСТРЕННОЕ ВОССТАНОВЛЕНИЕ: сброшено до {self.consecutive_errors} ошибок, активирован режим восстановления")
                
                # Отправляем уведомление
                alert_message = (
                    f"🚨 <b>ЭКСТРЕННОЕ ВОССТАНОВЛЕНИЕ МОНИТОРИНГА</b>\n\n"
                    f"⚠️ <b>Проблема:</b> критическая перегрузка ошибок\n"
                    f"🔧 <b>Действие:</b> активирован режим восстановления\n"
                    f"📊 <b>Ошибки сброшены:</b> {self.consecutive_errors * 2} → {self.consecutive_errors}\n\n"
                    f"🔄 <b>Мониторинг продолжается в усиленном режиме</b>"
                )
                send_telegram(alert_message)
                
        except Exception as e:
            logger.error(f"❌ Ошибка экстренной очистки мониторинга: {e}")

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
        
        monitor_cycle_count = 0
        while self.running:
            try:
                await self.monitor_cycle()
                monitor_cycle_count += 1
                
                # Проверяем перегрузку каждые 10 циклов
                if monitor_cycle_count % 10 == 0:
                    await self.emergency_clear_monitor_overload()
                
                # Небольшая пауза только если нет токенов для мониторинга
                # Иначе сразу переходим к следующему циклу
                logger.info(f"⚡ Переход к следующему циклу мониторинга... (#{monitor_cycle_count})")
                
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в мониторинге: {e}")
                self.consecutive_errors += 1
                await asyncio.sleep(5)  # Пауза при ошибке
    
    def stop_monitoring(self):
        """Останавливает мониторинг"""
        self.running = False
        logger.info("🛑 Остановка фонового мониторинга...")

    async def get_contract_mentions_with_authors(self, token, proxy, cycle_cookie):
        """Получает HTML ответы для парсинга авторов С БЫСТРЫМИ ТАЙМАУТАМИ"""
        try:
            # Добавляем вчерашнюю дату и убираем поиск с кавычками (UTC)
            from datetime import datetime, timedelta
            yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            # Делаем только один запрос без кавычек
            urls = [
                f"https://nitter.tiekoetter.com/search?f=tweets&q={token.mint}&since={yesterday}&until=&near="
            ]
            
            headers_with_cookie = self.headers.copy()
            headers_with_cookie['Cookie'] = cycle_cookie
            
            all_authors = []
            tweets_count = 0
            engagement = 0
            
            for url in urls:
                try:
                    # ОПТИМИЗАЦИЯ: быстрый таймаут 5 секунд (быстрее чем pump_bot)
                    # Настройка прокси если требуется
                    connector = None
                    request_kwargs = {}
                    if proxy:
                        try:
                            # Пробуем новый API (aiohttp 3.8+)
                            connector = aiohttp.ProxyConnector.from_url(proxy)
                            proxy_info = proxy.split('@')[1] if '@' in proxy else proxy
                            logger.debug(f"🌐 Фоновый мониторинг использует прокси через ProxyConnector: {proxy_info}")
                        except AttributeError:
                            # Для aiohttp 3.9.1 - прокси передается напрямую в get()
                            connector = aiohttp.TCPConnector()
                            request_kwargs['proxy'] = proxy
                            proxy_info = proxy.split('@')[1] if '@' in proxy else proxy
                            logger.debug(f"🌐 Фоновый мониторинг использует прокси напрямую: {proxy_info}")
                    
                    async with aiohttp.ClientSession(connector=connector) as session:
                        async with session.get(url, headers=headers_with_cookie, timeout=5, **request_kwargs) as response:
                            if response.status == 200:
                                html = await response.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Проверяем на блокировку
                                title = soup.find('title')
                                if title and 'Making sure you\'re not a bot!' in title.get_text():
                                    logger.error(f"🤖 ФОНОВЫЙ МОНИТОРИНГ: БЛОКИРОВКА для {token.symbol}")
                                    logger.error(f"📋 ПРИЧИНА: защита Nitter от ботов ('Making sure you're not a bot!')")
                                    logger.error(f"🔧 ДЕЙСТВИЕ: требуется обновление cookie")
                                    logger.error(f"🍪 Cookie: {cycle_cookie}")
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
                                
                                # УСПЕХ: сбрасываем счетчик ошибок
                                self.consecutive_errors = max(0, self.consecutive_errors - 1)
                                
                            elif response.status == 429:
                                logger.warning(f"🚫 ФОНОВЫЙ МОНИТОРИНГ: 429 ОШИБКА для {token.symbol}")
                                logger.warning(f"📋 ПРИЧИНА: слишком много запросов к Nitter серверу")
                                logger.warning(f"🔧 ДЕЙСТВИЕ: быстрый пропуск токена")
                                self.consecutive_errors += 1
                                continue
                            else:
                                logger.warning(f"⚠️ Статус {response.status} для {token.symbol}")
                                self.consecutive_errors += 1
                                continue
                                
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ ФОНОВЫЙ МОНИТОРИНГ: ТАЙМАУТ для {token.symbol}")
                    logger.warning(f"📋 ПРИЧИНА: медленный ответ Nitter сервера (>5 секунд)")
                    logger.warning(f"🔧 ДЕЙСТВИЕ: пропускаем токен и переходим к следующему")
                    self.consecutive_errors += 1
                    continue
                except Exception as e:
                    # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ОШИБОК В ФОНОВОМ МОНИТОРЕ
                    error_type = type(e).__name__
                    error_msg = str(e)
                    
                    if "ConnectionError" in error_type:
                        logger.error(f"🔌 ФОНОВЫЙ МОНИТОРИНГ: ОШИБКА СОЕДИНЕНИЯ для {token.symbol}")
                        logger.error(f"📋 ПРИЧИНА: сеть недоступна или Nitter сервер недоступен")
                    elif "SSLError" in error_type:
                        logger.error(f"🔒 ФОНОВЫЙ МОНИТОРИНГ: SSL ОШИБКА для {token.symbol}")
                        logger.error(f"📋 ПРИЧИНА: проблемы с HTTPS сертификатом")
                    elif "HTTPError" in error_type:
                        logger.error(f"🌐 ФОНОВЫЙ МОНИТОРИНГ: HTTP ОШИБКА для {token.symbol}")
                        logger.error(f"📋 ПРИЧИНА: ошибка HTTP протокола")
                    else:
                        logger.error(f"❓ ФОНОВЫЙ МОНИТОРИНГ: НЕИЗВЕСТНАЯ ОШИБКА для {token.symbol}")
                        logger.error(f"📋 ТИП: {error_type}")
                    
                    logger.error(f"📄 ДЕТАЛИ: {error_msg}")
                    logger.error(f"🔧 ДЕЙСТВИЕ: пропускаем токен и переходим к следующему")
                    
                    self.consecutive_errors += 1
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
            self.consecutive_errors += 1
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