#!/usr/bin/env python3
"""
Фоновый мониторинг токенов для отслеживания появления адресов контрактов в Twitter
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from database import get_db_manager, Token
from pump_bot import search_single_query, send_telegram, send_telegram_photo, extract_tweet_authors, TWITTER_AUTHOR_BLACKLIST, analyze_author_contract_diversity, analyze_author_page_contracts
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
        self.max_token_age_minutes = 20  # Мониторим токены не старше 20 минут
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
            # Токены созданные не более 20 минут назад (убираем фильтр по twitter_contract_tweets)
            cutoff_time = datetime.utcnow() - timedelta(minutes=self.max_token_age_minutes)
            
            tokens = session.query(Token).filter(
                Token.created_at >= cutoff_time,           # Не старше 20 минут
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
        УПРОЩЕННАЯ ЛОГИКА: Отправляем уведомления только если есть информация об авторах,
        кроме случаев когда автор отправляет каждое сообщение с контрактом (100% спам)
        ВАЖНО: Также проверяем черный список авторов
        """
        if not authors:
            logger.info(f"🚫 Нет информации об авторах твитов - пропускаем уведомление")
            return False  # Нет авторов - НЕ отправляем
        
        # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА ЧЕРНОГО СПИСКА
        blacklisted_authors = 0
        for author in authors:
            username = author.get('username', '').lower()
            if username in TWITTER_AUTHOR_BLACKLIST:
                blacklisted_authors += 1
                logger.info(f"🚫 Автор @{username} в черном списке - исключаем из анализа")
        
        # Если ВСЕ авторы в черном списке - блокируем уведомление
        if blacklisted_authors == len(authors):
            logger.info(f"🚫 ВСЕ авторы ({len(authors)}) в черном списке - блокируем уведомление")
            return False
        
        pure_spammers = 0  # Авторы которые КАЖДОЕ сообщение пишут с контрактом
        total_authors = len(authors)
        valid_authors = total_authors - blacklisted_authors  # Авторы НЕ из черного списка
        
        # Если нет валидных авторов после фильтрации - блокируем
        if valid_authors <= 0:
            logger.info(f"🚫 Нет валидных авторов после фильтрации черного списка - блокируем уведомление")
            return False
        
        for author in authors:
            diversity_percent = author.get('contract_diversity', 0)
            spam_percent = author.get('max_contract_spam', 0)
            total_tweets = author.get('total_contract_tweets', 0)
            username = author.get('username', 'Unknown')
            
            # Пропускаем авторов из черного списка в анализе спама
            if username.lower() in TWITTER_AUTHOR_BLACKLIST:
                logger.info(f"🚫 @{username}: В ЧЕРНОМ СПИСКЕ - пропускаем анализ спама")
                continue
            
            # ПРОСТАЯ ПРОВЕРКА: если автор пишет контракты в 90%+ сообщений = чистый спамер
            if total_tweets >= 3 and (spam_percent >= 90 or diversity_percent >= 90):
                pure_spammers += 1
                logger.info(f"🚫 @{username}: ЧИСТЫЙ СПАМЕР - контракты в {max(spam_percent, diversity_percent):.1f}% сообщений")
            else:
                logger.info(f"✅ @{username}: НОРМАЛЬНЫЙ АВТОР - контракты в {max(spam_percent, diversity_percent):.1f}% сообщений")
        
        # Блокируем ТОЛЬКО если ВСЕ НЕЗАБЛОКИРОВАННЫЕ авторы - чистые спамеры
        should_notify = pure_spammers < valid_authors
        
        logger.info(f"📊 УПРОЩЕННЫЙ АНАЛИЗ АВТОРОВ:")
        logger.info(f"   👥 Всего авторов: {total_authors}")
        logger.info(f"   🚫 В черном списке: {blacklisted_authors}")
        logger.info(f"   ✅ Валидных авторов: {valid_authors}")
        logger.info(f"   🚫 Чистых спамеров (90%+ контрактов): {pure_spammers}")
        logger.info(f"   ✅ Нормальных авторов: {valid_authors - pure_spammers}")
        logger.info(f"   🎯 РЕШЕНИЕ: {'ОТПРАВИТЬ' if should_notify else 'ЗАБЛОКИРОВАТЬ'}")
        
        if not should_notify:
            logger.info(f"🚫 Уведомление заблокировано - ВСЕ авторы являются чистыми спамерами")
        else:
            logger.info(f"✅ Уведомление разрешено - есть нормальные авторы или нет данных об авторах")
        
        return should_notify

    async def send_contract_alert(self, token, tweets_count, engagement, authors, is_first_discovery=True):
        """Отправляет уведомление о найденном контракте в Twitter"""
        try:
            emoji = "🔥" if is_first_discovery else "🚨"
            title = "КОНТРАКТ НАЙДЕН В TWITTER!" if is_first_discovery else f"НОВАЯ АКТИВНОСТЬ ПО КОНТРАКТУ! +{tweets_count - (token.twitter_contract_tweets or 0)} новых твитов!"
            
            # Получаем дату создания токена
            token_created_at = token.created_at.strftime('%Y-%m-%d %H:%M:%S') if token.created_at else "Неизвестно"
            
            message = (
                f"{emoji} <b>{title}</b>\n\n"
                f"🪙 <b>Токен:</b> {token.symbol or 'Unknown'}\n"
                f"💰 <b>Название:</b> {token.name or 'N/A'}\n"
                f"📄 <b>Контракт:</b> <code>{token.mint}</code>\n"
                f"📅 <b>Создан:</b> {token_created_at}\n"
            )
            
            # Добавляем информацию о твитах
            if is_first_discovery:
                action_text = f"📱 <b>Твитов с контрактом:</b> {tweets_count}"
            else:
                previous_tweets = token.twitter_contract_tweets or 0
                new_tweets = tweets_count - previous_tweets
                action_text = f"📱 <b>Всего твитов:</b> {tweets_count} (+{new_tweets} новых)"
            
            message += f"\n📊 <b>Активность:</b> {engagement}\n"
            
            # Добавляем Market Cap только если он больше 0
            if token.market_cap and token.market_cap > 0:
                message += f"📈 <b>Текущий Market Cap:</b> ${token.market_cap:,.0f}\n"
            
            message += (
                f"\n{action_text}\n"
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
                    tweet_text = author.get('tweet_text', '')  # Полный текст твита
                    tweet_date = author.get('tweet_date', '')  # Дата твита
                    
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
                    
                    # Полная информация о профиле
                    following_count = author.get('following_count', 0)
                    tweets_count = author.get('tweets_count', 0)
                    likes_count = author.get('likes_count', 0)
                    join_date = author.get('join_date', '')
                    
                    if followers > 0 or following_count > 0 or tweets_count > 0:
                        message += f"   👥 {followers:,} подписчиков | {following_count:,} подписок\n"
                        message += f"   📝 {tweets_count:,} твитов | ❤️ {likes_count:,} лайков\n"
                        if join_date:
                            message += f"   📅 Создан: {join_date}\n"
                    
                    # Добавляем дату публикации если есть
                    if tweet_date:
                        message += f"   📅 Опубликован: {tweet_date}\n"
                    
                    # Добавляем тип твита
                    tweet_type = author.get('tweet_type', 'Твит')
                    type_emoji = "💬" if tweet_type == "Ответ" else "🐦"
                    message += f"   {type_emoji} Тип: {tweet_type}\n"
                    
                    # Добавляем исторические данные автора (используем уже загруженные данные)
                    historical_data = author.get('historical_data', {})
                    if historical_data and historical_data.get('total_mentions', 0) > 0:
                        total_mentions = historical_data.get('total_mentions', 0)
                        unique_tokens = historical_data.get('unique_tokens', 0)
                        recent_7d = historical_data.get('recent_mentions_7d', 0)
                        recent_30d = historical_data.get('recent_mentions_30d', 0)
                        
                        message += f"   📊 История: {total_mentions} упоминаний ({unique_tokens} токенов)\n"
                        if recent_7d > 0 or recent_30d > 0:
                            message += f"   📈 Активность: {recent_7d} за 7д, {recent_30d} за 30д\n"
                    
                    # Показываем анализ концентрации контрактов
                    if total_contract_tweets > 0:
                        message += f"   📊 Контракты: {unique_contracts} из {total_contract_tweets} твитов (концентрация: {spam_percent:.1f}%)\n"
                        message += f"   🎯 Анализ: {spam_analysis}\n"
                    
                    # Весь текст твита в цитате
                    if tweet_text:
                        message += f"   💬 <blockquote>{tweet_text}</blockquote>\n"
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
            
            # Получаем URL картинки токена
            token_image_url = f"https://axiomtrading.sfo3.cdn.digitaloceanspaces.com/{token.mint}.webp"
            
            send_telegram_photo(token_image_url, message, keyboard)
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
                batch_size = 60  # Увеличен оптимальный размер: 30→60
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
            f"📊 <b>Мониторим токены:</b> не старше {self.max_token_age_minutes} минут\n"
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
                                    # Извлекаем авторов с дополнительной информацией о типе твита
                                    for tweet in tweets:
                                        # Проверяем наличие retweet-header - если есть, то это ретвит
                                        retweet_header = tweet.find('div', class_='retweet-header')
                                        if retweet_header:
                                            continue  # Пропускаем ретвиты
                                        
                                        # Извлекаем имя автора
                                        author_link = tweet.find('a', class_='username')
                                        if author_link:
                                            author_username = author_link.get_text(strip=True).replace('@', '')
                                            
                                            # Определяем тип твита
                                            replying_to = tweet.find('div', class_='replying-to')
                                            tweet_type = "Ответ" if replying_to else "Твит"
                                            
                                            # Извлекаем текст твита
                                            tweet_content = tweet.find('div', class_='tweet-content')
                                            tweet_text = tweet_content.get_text(strip=True) if tweet_content else ""
                                            
                                            # Извлекаем дату твита
                                            tweet_date = tweet.find('span', class_='tweet-date')
                                            tweet_date_text = ""
                                            if tweet_date:
                                                # Ищем ссылку с датой
                                                date_link = tweet_date.find('a')
                                                if date_link:
                                                    tweet_date_text = date_link.get('title')
                                                else:
                                                    # Если нет ссылки, берем текст напрямую
                                                    tweet_date_text = tweet_date.get_text(strip=True)
                                            
                                            # Проверяем наличие контракта в твите
                                            if token.mint in tweet_text:
                                                all_authors.append({
                                                    'username': author_username,
                                                    'tweet_text': tweet_text,
                                                    'tweet_type': tweet_type,
                                                    'tweet_date': tweet_date_text,
                                                    'query': token.mint
                                                })
                                    
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
            
            # ЗАГРУЖАЕМ ПРОФИЛИ АВТОРОВ (как в pump_bot.py)
            if unique_authors:
                logger.info(f"👥 Загружаем профили {len(unique_authors)} авторов для фонового мониторинга...")
                
                # Проверяем существующих авторов в БД
                from database import get_db_manager, TwitterAuthor
                from twitter_profile_parser import TwitterProfileParser
                from datetime import datetime
                
                db_manager = get_db_manager()
                usernames_to_parse = []
                usernames_to_update = []
                existing_authors = {}
                
                for author in unique_authors:
                    username = author['username']
                    
                    # Проверяем в БД
                    session = db_manager.Session()
                    try:
                        existing_author = session.query(TwitterAuthor).filter_by(username=username).first()
                        if existing_author:
                            # Проверяем возраст данных (обновляем если старше 20 минут)
                            time_since_update = datetime.utcnow() - existing_author.last_updated
                            minutes_since_update = time_since_update.total_seconds() / 60
                            
                            if minutes_since_update >= 20:
                                # Данные устарели - нужно обновить
                                usernames_to_update.append(username)
                                existing_authors[username] = {
                                    'username': existing_author.username,
                                    'display_name': existing_author.display_name,
                                    'followers_count': existing_author.followers_count,
                                    'following_count': existing_author.following_count,
                                    'tweets_count': existing_author.tweets_count,
                                    'likes_count': existing_author.likes_count,
                                    'bio': existing_author.bio,
                                    'website': existing_author.website,
                                    'join_date': existing_author.join_date,
                                    'is_verified': existing_author.is_verified,
                                    'avatar_url': existing_author.avatar_url
                                }
                                logger.info(f"🔄 Автор @{username} найден в БД, но данные устарели ({minutes_since_update:.1f}мин) - нужно обновление")
                            else:
                                # Данные свежие - используем из БД
                                existing_authors[username] = {
                                    'username': existing_author.username,
                                    'display_name': existing_author.display_name,
                                    'followers_count': existing_author.followers_count,
                                    'following_count': existing_author.following_count,
                                    'tweets_count': existing_author.tweets_count,
                                    'likes_count': existing_author.likes_count,
                                    'bio': existing_author.bio,
                                    'website': existing_author.website,
                                    'join_date': existing_author.join_date,
                                    'is_verified': existing_author.is_verified,
                                    'avatar_url': existing_author.avatar_url
                                }
                                logger.info(f"📋 Автор @{username} найден в БД ({existing_author.followers_count:,} подписчиков, обновлен {minutes_since_update:.1f}мин назад)")
                        else:
                            # Автор не найден - нужно загрузить профиль
                            usernames_to_parse.append(username)
                            logger.info(f"🔍 Автор @{username} не найден в БД - нужна загрузка")
                    finally:
                        session.close()
                
                # Загружаем новых авторов и обновляем устаревшие
                new_profiles = {}
                updated_profiles = {}
                total_to_load = len(usernames_to_parse) + len(usernames_to_update)
                
                if total_to_load > 0:
                    logger.info(f"📥 Загружаем {len(usernames_to_parse)} новых и обновляем {len(usernames_to_update)} устаревших профилей...")
                    
                    # Используем контекстный менеджер для парсера
                    async with TwitterProfileParser() as profile_parser:
                        # Загружаем новые профили
                        if usernames_to_parse:
                            new_profiles = await profile_parser.get_multiple_profiles(usernames_to_parse)
                        
                        # Обновляем устаревшие профили
                        if usernames_to_update:
                            updated_profiles = await profile_parser.get_multiple_profiles(usernames_to_update)
                else:
                    logger.info(f"✅ Все авторы найдены в БД с актуальными данными - пропускаем загрузку профилей")
                
                # Обогащаем данные авторов профилями
                for author in unique_authors:
                    username = author['username']
                    
                    # Приоритет: обновленные данные > новые данные > существующие в БД
                    profile = updated_profiles.get(username) or new_profiles.get(username) or existing_authors.get(username)
                    
                    if profile and isinstance(profile, dict):
                        # Получаем исторические данные автора
                        historical_data = db_manager.get_author_historical_data(username)
                        
                        author.update({
                            'display_name': profile.get('display_name', ''),
                            'followers_count': profile.get('followers_count', 0),
                            'following_count': profile.get('following_count', 0),
                            'tweets_count': profile.get('tweets_count', 0),
                            'likes_count': profile.get('likes_count', 0),
                            'bio': profile.get('bio', ''),
                            'website': profile.get('website', ''),
                            'join_date': profile.get('join_date', ''),
                            'is_verified': profile.get('is_verified', False),
                            'avatar_url': profile.get('avatar_url', ''),
                            # Исторические данные
                            'historical_data': historical_data
                        })
                        
                        # ДОБАВЛЯЕМ АНАЛИЗ КОНТРАКТОВ (как в pump_bot.py)
                        
                        # Собираем все твиты этого автора с текущей страницы
                        author_tweets_on_page = []
                        for author_data in unique_authors:
                            if author_data['username'] == username:
                                author_tweets_on_page.append(author_data['tweet_text'])
                        
                        # ВСЕГДА загружаем полные данные с профиля для точного анализа
                        logger.info(f"🔍 Анализируем контракты автора @{username} (загружаем с профиля)")
                        page_analysis = await analyze_author_page_contracts(username, tweets_on_page=None, load_from_profile=True)
                        
                        # Проверяем что получили достаточно данных
                        total_analyzed_tweets = page_analysis['total_tweets_on_page']
                        
                        # Обрабатываем разные случаи недостатка данных
                        if total_analyzed_tweets < 3:
                            if page_analysis['diversity_category'] == 'Сетевая ошибка':
                                # Сетевая ошибка - НЕ помечаем как подозрительного
                                logger.warning(f"🌐 @{username}: сетевая ошибка при анализе - пропускаем без блокировки")
                                page_analysis['is_spam_likely'] = False
                                page_analysis['recommendation'] = "🌐 Сетевая ошибка - повторить позже"
                            else:
                                # ИСПРАВЛЕННАЯ ЛОГИКА: мало твитов = потенциальный сигнал (новый аккаунт)
                                logger.info(f"🆕 @{username}: новый аккаунт с {total_analyzed_tweets} твитами - потенциальный сигнал!")
                                page_analysis['is_spam_likely'] = False  # НЕ спамер!
                                page_analysis['spam_analysis'] = f"Новый аккаунт: {total_analyzed_tweets} твитов (потенциальный сигнал)"
                                page_analysis['recommendation'] = "🆕 НОВЫЙ АККАУНТ - хороший сигнал"
                        
                        author.update({
                            'contract_diversity': page_analysis['contract_diversity_percent'],
                            'max_contract_spam': page_analysis['max_contract_spam_percent'],
                            'diversity_recommendation': page_analysis['recommendation'],
                            'is_spam_likely': page_analysis['is_spam_likely'],
                            'diversity_category': page_analysis['diversity_category'],
                            'spam_analysis': page_analysis['spam_analysis'],
                            'total_contract_tweets': page_analysis['total_tweets_on_page'],
                            'unique_contracts_count': page_analysis['unique_contracts_on_page']
                        })
                        
                        logger.info(f"📊 @{username}: {page_analysis['total_tweets_on_page']} твитов, концентрация: {page_analysis['max_contract_spam_percent']:.1f}%, разнообразие: {page_analysis['contract_diversity_percent']:.1f}% - {page_analysis['recommendation']}")
                        
                        # СОХРАНЯЕМ ПРОФИЛИ В БД (как в pump_bot.py)
                        
                        # Сохраняем новые профили в БД
                        if username in usernames_to_parse:
                            try:
                                db_manager.save_twitter_author(profile)
                                db_manager.save_tweet_mention({
                                    'mint': token.mint,  # Адрес контракта токена
                                    'author_username': username,
                                    'tweet_text': author['tweet_text'],
                                    'search_query': token.mint,
                                    'retweets': 0,  # В фоновом мониторинге нет данных о ретвитах
                                    'likes': 0,     # В фоновом мониторинге нет данных о лайках
                                    'replies': 0,   # В фоновом мониторинге нет данных об ответах
                                    'author_followers_at_time': profile.get('followers_count', 0),
                                    'author_verified_at_time': profile.get('is_verified', False)
                                })
                                logger.info(f"💾 Сохранен новый профиль @{username} в БД ({profile.get('followers_count', 0):,} подписчиков)")
                            except Exception as e:
                                logger.error(f"❌ Ошибка сохранения профиля @{username}: {e}")
                        
                        # Обновляем существующие профили в БД
                        elif username in usernames_to_update:
                            try:
                                # Обновляем профиль в БД
                                session = db_manager.Session()
                                try:
                                    existing_author = session.query(TwitterAuthor).filter_by(username=username).first()
                                    if existing_author:
                                        # Отслеживаем изменения для логирования
                                        old_followers = existing_author.followers_count
                                        new_followers = profile.get('followers_count', 0)
                                        followers_change = new_followers - old_followers
                                        
                                        # Обновляем все поля
                                        existing_author.display_name = profile.get('display_name', existing_author.display_name)
                                        existing_author.followers_count = new_followers
                                        existing_author.following_count = profile.get('following_count', existing_author.following_count)
                                        existing_author.tweets_count = profile.get('tweets_count', existing_author.tweets_count)
                                        existing_author.likes_count = profile.get('likes_count', existing_author.likes_count)
                                        existing_author.bio = profile.get('bio', existing_author.bio)
                                        existing_author.website = profile.get('website', existing_author.website)
                                        existing_author.join_date = profile.get('join_date', existing_author.join_date)
                                        existing_author.is_verified = profile.get('is_verified', existing_author.is_verified)
                                        existing_author.avatar_url = profile.get('avatar_url', existing_author.avatar_url)
                                        existing_author.last_updated = datetime.utcnow()
                                        
                                        session.commit()
                                        
                                        change_info = f" ({followers_change:+,} подписчиков)" if followers_change != 0 else ""
                                        logger.info(f"🔄 Обновлен профиль @{username} в БД ({new_followers:,} подписчиков{change_info})")
                                finally:
                                    session.close()
                                
                                # Сохраняем твит
                                db_manager.save_tweet_mention({
                                    'mint': token.mint,
                                    'author_username': username,
                                    'tweet_text': author['tweet_text'],
                                    'search_query': token.mint,
                                    'retweets': 0,
                                    'likes': 0,
                                    'replies': 0,
                                    'author_followers_at_time': profile.get('followers_count', 0),
                                    'author_verified_at_time': profile.get('is_verified', False)
                                })
                            except Exception as e:
                                logger.error(f"❌ Ошибка обновления профиля @{username}: {e}")
                        
                        # Для существующих авторов (с актуальными данными) сохраняем только твит
                        else:
                            try:
                                db_manager.save_tweet_mention({
                                    'mint': token.mint,
                                    'author_username': username,
                                    'tweet_text': author['tweet_text'],
                                    'search_query': token.mint,
                                    'retweets': 0,
                                    'likes': 0,
                                    'replies': 0,
                                    'author_followers_at_time': profile.get('followers_count', 0),
                                    'author_verified_at_time': profile.get('is_verified', False)
                                })
                            except Exception as e:
                                logger.error(f"❌ Ошибка сохранения твита @{username}: {e}")
                    else:
                        # Если профиль не загрузился, используем базовые данные
                        logger.warning(f"⚠️ Не удалось загрузить/найти профиль @{username}")
                        author.update({
                            'display_name': f'@{username}',
                            'followers_count': 0,
                            'following_count': 0,
                            'tweets_count': 0,
                            'likes_count': 0,
                            'bio': '',
                            'website': '',
                            'join_date': '',
                            'is_verified': False,
                            'avatar_url': '',
                            'historical_data': {}
                        })
            
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