#!/usr/bin/env python3
"""
Фоновый мониторинг токенов для отслеживания появления адресов контрактов в Twitter
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from database import get_db_manager, Token
from pump_bot import search_single_query, send_telegram, send_telegram_photo, extract_tweet_authors, TWITTER_AUTHOR_BLACKLIST, analyze_author_contract_diversity, analyze_author_page_contracts, is_spam_bot_tweet, should_notify_based_on_authors_unified, filter_authors_for_display, format_authors_section, was_twitter_notification_sent_recently, mark_twitter_notification_sent
from cookie_rotation import background_proxy_cookie_rotator, background_cookie_rotator
from logger_config import setup_logging
from twitter_profile_parser import TwitterProfileParser
import re
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote  # Добавляем import для URL-кодирования

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

def ensure_nitter_params(url):
    """Гарантирует наличие пустых параметров since, until, near в Nitter URL"""
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # Добавляем пустые параметры если их нет
        if 'since' not in query_params:
            query_params['since'] = ['']
        if 'until' not in query_params:
            query_params['until'] = ['']
        if 'near' not in query_params:
            query_params['near'] = ['']
        
        # Пересобираем URL
        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
        
    except Exception as e:
        logger.debug(f"Ошибка обработки URL параметров: {e}")
        return url

class BackgroundTokenMonitor:
    """Фоновый мониторинг токенов"""
    
    def __init__(self):
        self.db_manager = get_db_manager()
        self.running = False
        self.max_token_age_minutes = 5  # Мониторим токены не старше 5 минут
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
            # Токены созданные не более 5 минут назад (убираем фильтр по twitter_contract_tweets)
            cutoff_time = datetime.utcnow() - timedelta(minutes=self.max_token_age_minutes)
            
            tokens = session.query(Token).filter(
                Token.created_at >= cutoff_time,           # Не старше 5 минут
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
                        should_notify = should_notify_based_on_authors_unified(authors)
                        
                        if should_notify:
                            # ОТПРАВЛЯЕМ УВЕДОМЛЕНИЯ ТОЛЬКО ПРИ ПЕРВОМ ОБНАРУЖЕНИИ
                            if previous_tweets == 0:
                                # Первое обнаружение контракта - отправляем уведомление
                                if db_token.notification_sent:
                                    logger.info(f"🚫 Фоновое уведомление для {token.symbol} пропущено - уже было отложенное уведомление от основного бота")
                                else:
                                    await self.send_contract_alert(token, tweets_count, engagement, authors, is_first_discovery=True)
                                    
                                    # ❌ АВТОПОКУПКА TWITTER ТОКЕНОВ ОТКЛЮЧЕНА для экономии баланса  
                                    logger.info(f"💡 Автопокупка для Twitter токена {token.symbol} отключена (экономия баланса)")
                                    logger.info(f"💰 Сэкономлено: 0.001 SOL на токене {token.symbol}")
                            else:
                                # Новая активность - НЕ отправляем уведомления
                                logger.info(f"📈 {token.symbol}: обнаружена новая активность (+{new_tweets_found} твитов), но уведомления о новой активности отключены")
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
    


    async def execute_auto_purchase_twitter_token(self, mint, symbol, token_name):
        """Выполняет автоматическую покупку токена при первом обнаружении в Twitter"""
        try:
            logger.info(f"💰 АВТОПОКУПКА TWITTER ТОКЕНА: {symbol} ({mint[:8]}...)")
            
            # Импортируем axiom_trader
            from axiom_trader import execute_axiom_purchase
            
            # Параметры автопокупки для Twitter токенов (больше чем для новых токенов)
            auto_buy_amount = 0.001  # 0.001 SOL для Twitter токенов
            
            # Импортируем функцию газа
            try:
                from vip_config import get_gas_fee, get_gas_description
                gas_fee = get_gas_fee('twitter_tokens')
                gas_desc = get_gas_description('twitter_tokens')
                logger.info(f"⚡ Газ для Twitter токена: {gas_desc}")
            except ImportError:
                gas_fee = 0.002  # Fallback значение
            
            # Выполняем покупку через Axiom
            result = await execute_axiom_purchase(
                contract_address=mint,
                twitter_username="SolSpider_Twitter_AutoBuy",
                tweet_text=f"Автоматическая покупка при обнаружении в Twitter: {token_name} ({symbol})",
                sol_amount=auto_buy_amount,
                slippage=15,
                priority_fee=gas_fee  # Оптимизированный газ для Twitter токенов
            )
            
            if result.get('success', False):
                logger.info(f"✅ Twitter автопокупка {symbol} успешна! TX: {result.get('tx_hash', 'N/A')[:16]}...")
                
                # Отправляем уведомление об успешной покупке
                purchase_msg = (
                    f"💰 <b>TWITTER АВТОПОКУПКА ВЫПОЛНЕНА!</b>\n\n"
                    f"🪙 <b>{token_name or 'Unknown'}</b> ({symbol})\n"
                    f"📍 <b>Mint:</b> <code>{mint}</code>\n"
                    f"⚡ <b>Сумма:</b> {auto_buy_amount} SOL\n"
                    f"🔗 <b>TX:</b> <code>{result.get('tx_hash', 'N/A')}</code>\n"
                    f"⏱️ <b>Время:</b> {result.get('execution_time', 0):.2f}с\n"
                    f"🎯 <b>Причина:</b> Первое обнаружение в Twitter"
                )
                
                # Создаем клавиатуру с ссылками
                keyboard = [
                    [
                        {"text": "💎 Axiom.trade", "url": f"https://axiom.trade/t/{mint}"},
                        {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{mint}"}
                    ],
                    [{"text": "🚀 Pump.fun", "url": f"https://pump.fun/{mint}"}]
                ]
                
                send_telegram(purchase_msg, keyboard)
                
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"❌ Ошибка Twitter автопокупки {symbol}: {error_msg}")
        
                # Отправляем уведомление об ошибке
                error_notification = (
                    f"❌ <b>ОШИБКА TWITTER АВТОПОКУПКИ</b>\n\n"
                    f"🪙 <b>{token_name or 'Unknown'}</b> ({symbol})\n"
                    f"📍 <b>Mint:</b> <code>{mint}</code>\n"
                    f"⚠️ <b>Ошибка:</b> {error_msg[:100]}\n"
                    f"⚡ <b>Сумма:</b> {auto_buy_amount} SOL\n"
                    f"🎯 <b>Причина:</b> Первое обнаружение в Twitter"
                )
                
                send_telegram(error_notification)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка Twitter автопокупки {symbol}: {e}")
            
            # Отправляем уведомление о критической ошибке
            critical_error_msg = (
                f"🚫 <b>КРИТИЧЕСКАЯ ОШИБКА TWITTER АВТОПОКУПКИ</b>\n\n"
                f"🪙 <b>{token_name or 'Unknown'}</b> ({symbol})\n"
                f"📍 <b>Mint:</b> <code>{mint}</code>\n"
                f"❌ <b>Ошибка:</b> {str(e)[:100]}\n"
                f"🎯 <b>Причина:</b> Первое обнаружение в Twitter"
            )
            
            send_telegram(critical_error_msg)
            
            return {
                'success': False,
                'error': f'Critical error: {str(e)}',
                'execution_time': 0
            }

    async def send_contract_alert(self, token, tweets_count, engagement, authors, is_first_discovery=True):
        """Отправляет уведомление о найденном контракте в Twitter (только первое обнаружение)"""
        try:
            # ПРОВЕРКА ДЕДУПЛИКАЦИИ: не отправлялось ли уже уведомление недавно
            if was_twitter_notification_sent_recently(token.mint):
                logger.info(f"🔄 {token.symbol}: уведомление о Twitter активности уже отправлено недавно - пропускаем дублирование")
                return
            
            # Теперь отправляем только уведомления о первом обнаружении
            emoji = "🔥"
            title = "КОНТРАКТ НАЙДЕН В TWITTER!"
            
            # Получаем дату создания токена
            token_created_at = token.created_at.strftime('%Y-%m-%d %H:%M:%S') if token.created_at else "Неизвестно"
            
            message = (
                f"{emoji} <b>{title}</b>\n\n"
                f"🪙 <b>Токен:</b> {token.symbol or 'Unknown'}\n"
                f"💰 <b>Название:</b> {token.name or 'N/A'}\n"
                f"📄 <b>Контракт:</b> <code>{token.mint}</code>\n"
                f"📅 <b>Создан:</b> {token_created_at}\n"
            )
            
            # Информация о твитах (только первое обнаружение)
            action_text = f"📱 <b>Твитов с контрактом:</b> {tweets_count}"
            
            message += f"\n📊 <b>Активность:</b> {engagement}\n"
            
            # Добавляем Market Cap только если он больше 0
            if token.market_cap and token.market_cap > 0:
                message += f"📈 <b>Текущий Market Cap:</b> ${token.market_cap:,.0f}\n"
            
            message += (
                f"\n{action_text}\n"
                f"📈 <b>Возможен рост интереса к токену</b>\n\n"
            )
            
            # Используем единую функцию форматирования авторов
            message += format_authors_section(authors, prefix_newline=False)
            
            message += f"⚡ <b>Время действовать!</b>"
            
            # Создаем кнопки для уведомления
            keyboard = [
                [
                    {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/t/{token.mint}"},
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
            
            # Отмечаем что уведомление отправлено
            mark_twitter_notification_sent(token.mint)
            
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
        """Получает HTML ответы для парсинга авторов С БЫСТРЫМИ ТАЙМАУТАМИ и пагинацией"""
        try:
            # Убираем параметр since - ищем по всем твитам без временных ограничений
            # Делаем только один запрос с кавычками и пагинацией для точного поиска
            quoted_contract = quote(f'"{token.mint}"')  # URL-кодируем кавычки для правильной обработки
            base_url = f"https://nitter.tiekoetter.com/search?f=tweets&q={quoted_contract}&since=&until=&near="
            urls_to_process = [base_url]
            
            headers_with_cookie = self.headers.copy()
            headers_with_cookie['Cookie'] = cycle_cookie
            
            all_authors = []
            tweets_count = 0
            engagement = 0
            
            # ПАГИНАЦИЯ: проходим по страницам до максимума 3 страниц для фонового мониторинга
            page_count = 0
            max_pages = 3
            current_url = base_url
            
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
                while page_count < max_pages and current_url:
                    page_count += 1
                    logger.debug(f"📄 Фоновый мониторинг {token.symbol}: страница {page_count}/{max_pages}")
                    
                    try:
                        # ОПТИМИЗАЦИЯ: быстрый таймаут 5 секунд (быстрее чем pump_bot)
                        async with session.get(current_url, headers=headers_with_cookie, timeout=5, **request_kwargs) as response:
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
                                
                                # Подсчитываем твиты (исключаем элементы навигации)
                                tweets = soup.find_all('div', class_='timeline-item')
                                tweets = [t for t in tweets if not t.find('div', class_='show-more') and not t.find('div', class_='top-ref')]
                                page_tweets_count = len(tweets)
                                tweets_count += page_tweets_count
                                
                                logger.debug(f"📱 Фоновый мониторинг {token.symbol}: страница {page_count} содержит {page_tweets_count} твитов")
                                
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
                                
                                # Ищем ссылку на следующую страницу
                                if page_count < max_pages:
                                    show_more = soup.find('div', class_='show-more')
                                    if show_more:
                                        link = show_more.find('a')
                                        if link and 'href' in link.attrs:
                                            next_page_url = link['href']
                                            # Формируем полный URL
                                            if next_page_url.startswith('?'):
                                                current_url = f"https://nitter.tiekoetter.com/search{next_page_url}"
                                            elif next_page_url.startswith('/search'):
                                                current_url = f"https://nitter.tiekoetter.com{next_page_url}"
                                            else:
                                                current_url = next_page_url
                                            
                                            # Гарантируем наличие пустых параметров since, until, near
                                            current_url = ensure_nitter_params(current_url)
                                            logger.debug(f"🔗 Фоновый мониторинг {token.symbol}: следующая страница {current_url}")
                                            # Пауза между страницами
                                            await asyncio.sleep(0.3)
                                        else:
                                            current_url = None  # Нет больше страниц
                                    else:
                                        current_url = None  # Нет больше страниц
                                else:
                                    current_url = None  # Достигнут лимит страниц
                                
                            elif response.status == 429:
                                logger.warning(f"🚫 ФОНОВЫЙ МОНИТОРИНГ: 429 ОШИБКА для {token.symbol} на странице {page_count}")
                                logger.warning(f"📋 ПРИЧИНА: слишком много запросов к Nitter серверу")
                                logger.warning(f"🔧 ДЕЙСТВИЕ: останавливаем пагинацию")
                                self.consecutive_errors += 1
                                break  # Прерываем цикл пагинации
                            else:
                                logger.warning(f"⚠️ Статус {response.status} для {token.symbol} на странице {page_count}")
                                self.consecutive_errors += 1
                                break  # Прерываем цикл пагинации
                                
                    except asyncio.TimeoutError:
                        logger.warning(f"⏰ ФОНОВЫЙ МОНИТОРИНГ: ТАЙМАУТ для {token.symbol} на странице {page_count}")
                        logger.warning(f"📋 ПРИЧИНА: медленный ответ Nitter сервера (>5 секунд)")
                        logger.warning(f"🔧 ДЕЙСТВИЕ: останавливаем пагинацию")
                        self.consecutive_errors += 1
                        break  # Прерываем цикл пагинации
                    except Exception as e:
                        # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ОШИБОК В ФОНОВОМ МОНИТОРЕ
                        error_type = type(e).__name__
                        error_msg = str(e)
                        
                        if "ConnectionError" in error_type:
                            logger.error(f"🔌 ФОНОВЫЙ МОНИТОРИНГ: ОШИБКА СОЕДИНЕНИЯ для {token.symbol} на странице {page_count}")
                            logger.error(f"📋 ПРИЧИНА: сеть недоступна или Nitter сервер недоступен")
                        elif "SSLError" in error_type:
                            logger.error(f"🔒 ФОНОВЫЙ МОНИТОРИНГ: SSL ОШИБКА для {token.symbol} на странице {page_count}")
                            logger.error(f"📋 ПРИЧИНА: проблемы с HTTPS сертификатом")
                        elif "HTTPError" in error_type:
                            logger.error(f"🌐 ФОНОВЫЙ МОНИТОРИНГ: HTTP ОШИБКА для {token.symbol} на странице {page_count}")
                            logger.error(f"📋 ПРИЧИНА: ошибка HTTP протокола")
                        else:
                            logger.error(f"❓ ФОНОВЫЙ МОНИТОРИНГ: НЕИЗВЕСТНАЯ ОШИБКА для {token.symbol} на странице {page_count}")
                            logger.error(f"📋 ТИП: {error_type}")
                        
                        logger.error(f"📄 ДЕТАЛИ: {error_msg}")
                        logger.error(f"🔧 ДЕЙСТВИЕ: останавливаем пагинацию")
                        
                        self.consecutive_errors += 1
                        break  # Прерываем цикл пагинации
            
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
                            # Проверяем возраст данных (обновляем если старше 5 минут)
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