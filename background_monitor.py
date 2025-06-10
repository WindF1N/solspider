#!/usr/bin/env python3
"""
Фоновый мониторинг токенов для отслеживания появления адресов контрактов в Twitter
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from database import get_db_manager, Token
from pump_bot import search_single_query, send_telegram
from cookie_rotation import background_cookie_rotator
from logger_config import setup_logging

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
        """Получает токены для мониторинга (без контракта в Twitter)"""
        session = self.db_manager.Session()
        try:
            # Токены созданные не более 1 часа назад и без упоминаний контракта в Twitter
            cutoff_time = datetime.utcnow() - timedelta(hours=self.max_token_age_hours)
            
            tokens = session.query(Token).filter(
                Token.created_at >= cutoff_time,           # Не старше 1 часа
                Token.twitter_contract_tweets == 0,        # Нет твитов с контрактом
                Token.mint.isnot(None),                    # Есть адрес контракта
                Token.symbol.isnot(None)                   # Есть символ
            ).order_by(Token.created_at.desc()).all()
            
            logger.info(f"📊 Найдено {len(tokens)} токенов для фонового мониторинга")
            return tokens
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения токенов для мониторинга: {e}")
            return []
        finally:
            session.close()
    
    async def check_contract_mentions(self, token, cycle_cookie):
        """Проверяет появление упоминаний контракта в Twitter (с кавычками и без)"""
        try:
            # Делаем 2 запроса: с кавычками и без, используя один cookie для цикла
            results = await asyncio.gather(
                search_single_query(token.mint, self.headers, use_quotes=True, cycle_cookie=cycle_cookie),   # С кавычками
                search_single_query(token.mint, self.headers, use_quotes=False, cycle_cookie=cycle_cookie),  # Без кавычек
                return_exceptions=True
            )
            
            # Собираем все твиты в один словарь для дедупликации
            all_tweets = {}
            
            for i, result in enumerate(results):
                if isinstance(result, Exception) or not result:
                    continue
                    
                for tweet_data in result:
                    tweet_id = tweet_data['id']
                    engagement = tweet_data['engagement']
                    
                    # Если твит уже есть, берем максимальное значение активности
                    if tweet_id in all_tweets:
                        all_tweets[tweet_id] = max(all_tweets[tweet_id], engagement)
                    else:
                        all_tweets[tweet_id] = engagement
            
            # Итоговые подсчеты уникальных твитов
            tweets_count = len(all_tweets)
            engagement = sum(all_tweets.values())
            
            # Проверяем если возвращается 0,0 - возможно блокировка
            if tweets_count == 0 and engagement == 0:
                logger.debug(f"🔍 Контракт {token.symbol} не найден в Twitter (или блокировка)")
            
            if tweets_count > 0:
                logger.info(f"🎯 НАЙДЕН контракт {token.symbol} в Twitter! Уникальных твитов: {tweets_count}, активность: {engagement}")
                
                # Обновляем данные в БД
                session = self.db_manager.Session()
                try:
                    db_token = session.query(Token).filter_by(id=token.id).first()
                    if db_token:
                        db_token.twitter_contract_tweets = tweets_count
                        db_token.twitter_contract_found = True
                        db_token.updated_at = datetime.utcnow()
                        session.commit()
                        
                        logger.info(f"✅ Обновлена БД для токена {token.symbol}")
                        
                        # Отправляем уведомление
                        await self.send_contract_alert(token, tweets_count, engagement)
                        
                except Exception as e:
                    session.rollback()
                    logger.error(f"❌ Ошибка обновления БД для {token.symbol}: {e}")
                finally:
                    session.close()
                    
                return True
            else:
                logger.debug(f"🔍 Контракт {token.symbol} пока не найден в Twitter")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки контракта {token.symbol}: {e}")
            return False
    
    async def send_contract_alert(self, token, tweets_count, engagement):
        """Отправляет уведомление о найденном контракте"""
        try:
            # Вычисляем возраст токена
            age = datetime.utcnow() - token.created_at
            age_hours = age.total_seconds() / 3600
            
            message = (
                f"🔥 <b>КОНТРАКТ НАЙДЕН В TWITTER!</b>\n\n"
                f"💎 <b><a href='https://pump.fun/{token.mint}'>{token.name}</a></b>\n"
                f"🏷️ <b>Символ:</b> {token.symbol}\n"
                f"📍 <b>Mint:</b> <code>{token.mint}</code>\n"
                f"⏰ <b>Возраст токена:</b> {age_hours:.1f} часов\n"
                f"🐦 <b>Твиты с контрактом:</b> {tweets_count}\n"
                f"📊 <b>Активность:</b> {engagement}\n"
                f"📈 <b>Текущий Market Cap:</b> ${token.market_cap:,.0f}\n\n"
                f"🚀 <b>Пользователи начали делиться контрактом!</b>\n"
                f"📈 <b>Возможен рост интереса к токену</b>\n\n"
                f"⚡ <b>Время действовать!</b>"
            )
            
            # Кнопки для быстрых действий
            keyboard = [
                [
                    {"text": "💎 Купить на Axiom", "url": f"https://axiom.trade/meme/{token.bonding_curve_key or token.mint}"},
                    {"text": "⚡ QUICK BUY", "url": f"https://t.me/alpha_web3_bot?start=call-dex_men-SO-{token.mint}"}
                ],
                [
                    {"text": "📊 DexScreener", "url": f"https://dexscreener.com/solana/{token.mint}"}
                ]
            ]
            
            send_telegram(message, keyboard)
            logger.info(f"📨 Отправлено уведомление о контракте {token.symbol}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления о контракте {token.symbol}: {e}")
    
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
            f"🔍 <b>Отслеживаем:</b> появление адресов контрактов в Twitter\n"
            f"⚡ <b>Режим:</b> непрерывный мониторинг (без пауз)\n"
            f"📊 <b>Мониторим токены:</b> не старше {self.max_token_age_hours} часа\n"
            f"🔄 <b>Ротация:</b> 5 cookies + 7 прокси серверов\n"
            f"🎯 <b>Цель:</b> мгновенное обнаружение растущего интереса\n\n"
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