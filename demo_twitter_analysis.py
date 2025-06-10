#!/usr/bin/env python3
"""
Демонстрационный анализ корреляций между метриками авторов твитов и токенами
"""

import pandas as pd
import asyncio
from datetime import datetime, timedelta
import logging
import re
from dotenv import load_dotenv
from database import get_db_manager, Token
from twitter_profile_parser import TwitterProfileParser
from logger_config import setup_logging

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

class DemoTwitterAnalyzer:
    """Демонстрационный анализатор Twitter авторов"""
    
    def __init__(self):
        self.db_manager = get_db_manager()
        
    def create_sample_tweets(self, tokens):
        """Создает примеры обнаруженных твитов для анализа"""
        sample_tweets = []
        
        # Список популярных crypto аккаунтов для симуляции
        crypto_accounts = [
            {"username": "LaunchOnPump", "type": "bot"},
            {"username": "pumpdotfun", "type": "platform"},
            {"username": "solana", "type": "official"},
            {"username": "elonmusk", "type": "influencer"},
            {"username": "cz_binance", "type": "ceo"},
            {"username": "VitalikButerin", "type": "developer"},
            {"username": "SBF_FTX", "type": "ceo"},
            {"username": "justinsuntron", "type": "founder"},
            {"username": "APompliano", "type": "analyst"},
            {"username": "WClementeIII", "type": "analyst"}
        ]
        
        # Шаблоны твитов
        tweet_templates = [
            "🚀 New gem found! Check out {symbol} at {contract} - this could be huge! #crypto #solana",
            "RT @pumpdotfun: {symbol} just launched! Contract: {contract} 🔥",
            "📈 {symbol} is pumping! Contract address: {contract} - get in early!",
            "💎 Found another gem: {symbol} ({contract}) - thank me later 🚀",
            "🎯 New token alert: {symbol} - {contract} - looks promising!",
            "Breaking: {symbol} contract {contract} shows massive potential 📊",
            "Alpha alert 🚨 {symbol} ({contract}) is about to moon! DYOR",
            "Just ape'd into {symbol} - contract {contract} looks solid 💪",
            "Technical analysis on {symbol} ({contract}) looking bullish 📈",
            "Community is growing fast around {symbol} - {contract} 🚀"
        ]
        
        # Генерируем твиты для топ-20 токенов
        for i, token in enumerate(tokens[:10]):  # Ограничиваем 10 токенами для демо
            # Случайно выбираем автора и шаблон
            author = crypto_accounts[i % len(crypto_accounts)]
            template = tweet_templates[i % len(tweet_templates)]
            
            tweet_text = template.format(
                symbol=token.symbol,
                contract=token.mint
            )
            
            # Симулируем время создания твита (от 1 до 24 часов после создания токена)
            hours_after = (i % 24) + 1
            tweet_time = token.created_at + timedelta(hours=hours_after, minutes=i*3)
            
            sample_tweets.append({
                'token': token,
                'author_username': author['username'],
                'author_type': author['type'],
                'tweet_text': tweet_text,
                'tweet_created_at': tweet_time,
                'discovered_at': datetime.utcnow()
            })
        
        return sample_tweets
    
    async def analyze_sample_tweets_with_authors(self):
        """Анализирует примеры твитов с загрузкой реальных профилей авторов"""
        try:
            session = self.db_manager.Session()
            
            logger.info("🔍 Загружаем токены с найденными контрактами для демо...")
            
            # Получаем топ-20 токенов с контрактными твитами
            tokens = session.query(Token).filter(
                Token.twitter_contract_tweets > 0,
                Token.mint.isnot(None),
                Token.symbol.isnot(None)
            ).order_by(Token.twitter_contract_tweets.desc()).limit(20).all()
            
            logger.info(f"📊 Найдено {len(tokens)} токенов для анализа")
            
            if not tokens:
                logger.error("❌ Нет токенов с контрактными твитами для анализа")
                return []
            
            # Создаем примеры твитов
            sample_tweets = self.create_sample_tweets(tokens)
            logger.info(f"📱 Создано {len(sample_tweets)} примеров твитов")
            
            results = []
            unique_authors = set()
            
            # Анализируем профили авторов
            async with TwitterProfileParser() as profile_parser:
                for i, tweet_sample in enumerate(sample_tweets, 1):
                    logger.info(f"👤 Анализ автора {i}/{len(sample_tweets)}: @{tweet_sample['author_username']}")
                    
                    author_username = tweet_sample['author_username']
                    
                    # Загружаем профиль автора если еще не загружали
                    if author_username not in unique_authors:
                        profile_data = await profile_parser.get_profile(author_username)
                        
                        if profile_data:
                            unique_authors.add(author_username)
                            logger.info(f"✅ Загружен профиль @{author_username}: "
                                       f"{profile_data['followers_count']:,} подписчиков")
                            
                            # Добавляем результат
                            result = {
                                'token': tweet_sample['token'],
                                'tweet_data': tweet_sample,
                                'author_data': profile_data,
                                'author_type': tweet_sample['author_type']
                            }
                            results.append(result)
                        else:
                            logger.warning(f"⚠️ Не удалось загрузить профиль @{author_username}")
                    
                    # Пауза между запросами
                    await asyncio.sleep(2)
            
            session.close()
            return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа: {e}")
            return []
    
    def categorize_author_influence(self, author_data):
        """Категоризирует влияние автора"""
        followers = author_data['followers_count']
        is_verified = author_data['is_verified']
        
        if is_verified and followers > 1000000:
            return "Мега-инфлюенсер"
        elif is_verified and followers > 100000:
            return "Макро-инфлюенсер"
        elif followers > 100000:
            return "Большой инфлюенсер"
        elif followers > 10000:
            return "Средний инфлюенсер"
        elif followers > 1000:
            return "Микро-инфлюенсер"
        elif followers > 100:
            return "Нано-инфлюенсер"
        else:
            return "Обычный пользователь"
    
    def estimate_influence_potential(self, author_data):
        """Оценивает потенциал влияния автора"""
        followers = author_data['followers_count']
        tweets = author_data['tweets_count']
        is_verified = author_data['is_verified']
        
        # Простая система оценки
        score = 0
        
        # Подписчики
        if followers > 1000000:
            score += 100
        elif followers > 100000:
            score += 80
        elif followers > 10000:
            score += 60
        elif followers > 1000:
            score += 40
        elif followers > 100:
            score += 20
        
        # Верификация
        if is_verified:
            score += 30
        
        # Активность
        if tweets > 10000:
            score += 20
        elif tweets > 1000:
            score += 10
        
        # Категоризация
        if score >= 120:
            return "Критическое"
        elif score >= 100:
            return "Очень высокое"
        elif score >= 80:
            return "Высокое"
        elif score >= 60:
            return "Среднее"
        elif score >= 40:
            return "Низкое"
        else:
            return "Минимальное"
    
    def create_demo_analysis_excel(self, results):
        """Создает демонстрационный Excel отчет"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"demo_twitter_correlation_analysis_{timestamp}.xlsx"
            
            # 1. Основная таблица анализа
            main_analysis = []
            
            # 2. Сводка по авторам
            author_summary = []
            
            # 3. Анализ по типам авторов
            author_type_analysis = []
            
            # 4. Потенциальные корреляции
            correlation_insights = []
            
            # Обрабатываем результаты
            for result in results:
                token = result['token']
                tweet_data = result['tweet_data']
                author_data = result['author_data']
                author_type = result['author_type']
                
                # Основная таблица
                main_row = {
                    'Символ токена': token.symbol,
                    'Название токена': token.name or 'N/A',
                    'Market Cap': f"${token.market_cap:,.0f}" if token.market_cap else 'N/A',
                    'Возраст токена (ч)': f"{(datetime.utcnow() - token.created_at).total_seconds() / 3600:.1f}",
                    'Адрес контракта': token.mint,
                    
                    # Данные твита
                    'Текст твита': tweet_data['tweet_text'][:150] + '...' if len(tweet_data['tweet_text']) > 150 else tweet_data['tweet_text'],
                    'Время до твита (ч)': f"{(tweet_data['tweet_created_at'] - token.created_at).total_seconds() / 3600:.1f}",
                    
                    # Данные автора
                    'Автор': f"@{author_data['username']}",
                    'Имя автора': author_data['display_name'] or 'N/A',
                    'Тип автора': author_type.title(),
                    'Подписчики': f"{author_data['followers_count']:,}",
                    'Твиты': f"{author_data['tweets_count']:,}",
                    'Подписки': f"{author_data['following_count']:,}",
                    'Лайки': f"{author_data['likes_count']:,}",
                    'Верифицирован': 'Да' if author_data['is_verified'] else 'Нет',
                    'Дата регистрации': author_data['join_date'] or 'N/A',
                    
                    # Анализ влияния
                    'Категория влияния': self.categorize_author_influence(author_data),
                    'Потенциал влияния': self.estimate_influence_potential(author_data),
                    'Engagement Rate': f"{(author_data['likes_count'] / max(author_data['tweets_count'], 1)):.2f}",
                    'Follow Ratio': f"{(author_data['followers_count'] / max(author_data['following_count'], 1)):.1f}",
                    
                    # Ссылки
                    'Профиль Twitter': f"https://nitter.tiekoetter.com/{author_data['username']}",
                    'DexScreener': f"https://dexscreener.com/solana/{token.mint}",
                    'Pump.fun': f"https://pump.fun/{token.mint}"
                }
                main_analysis.append(main_row)
            
            # Сводка по авторам
            unique_authors = {}
            for result in results:
                author_data = result['author_data']
                if author_data['username'] not in unique_authors:
                    unique_authors[author_data['username']] = {
                        'data': author_data,
                        'type': result['author_type'],
                        'mentioned_tokens': 1
                    }
                else:
                    unique_authors[author_data['username']]['mentioned_tokens'] += 1
            
            for username, info in unique_authors.items():
                author_data = info['data']
                author_row = {
                    'Username': f"@{username}",
                    'Отображаемое имя': author_data['display_name'] or 'N/A',
                    'Тип аккаунта': info['type'].title(),
                    'Подписчики': author_data['followers_count'],
                    'Твиты': author_data['tweets_count'],
                    'Подписки': author_data['following_count'],
                    'Лайки': author_data['likes_count'],
                    'Верифицирован': 'Да' if author_data['is_verified'] else 'Нет',
                    'Дата регистрации': author_data['join_date'] or 'N/A',
                    'Упомянуто токенов': info['mentioned_tokens'],
                    'Категория влияния': self.categorize_author_influence(author_data),
                    'Потенциал влияния': self.estimate_influence_potential(author_data),
                    'Профиль': f"https://nitter.tiekoetter.com/{username}"
                }
                author_summary.append(author_row)
            
            # Анализ по типам авторов
            type_stats = {}
            for result in results:
                author_type = result['author_type']
                author_data = result['author_data']
                
                if author_type not in type_stats:
                    type_stats[author_type] = {
                        'count': 0,
                        'total_followers': 0,
                        'verified_count': 0,
                        'usernames': []
                    }
                
                type_stats[author_type]['count'] += 1
                type_stats[author_type]['total_followers'] += author_data['followers_count']
                if author_data['is_verified']:
                    type_stats[author_type]['verified_count'] += 1
                type_stats[author_type]['usernames'].append(f"@{author_data['username']}")
            
            for author_type, stats in type_stats.items():
                avg_followers = stats['total_followers'] / stats['count'] if stats['count'] > 0 else 0
                type_row = {
                    'Тип автора': author_type.title(),
                    'Количество': stats['count'],
                    'Средние подписчики': f"{avg_followers:,.0f}",
                    'Верифицированных': stats['verified_count'],
                    '% верифицированных': f"{(stats['verified_count'] / stats['count'] * 100):.1f}%" if stats['count'] > 0 else '0%',
                    'Примеры аккаунтов': ', '.join(stats['usernames'][:3])
                }
                author_type_analysis.append(type_row)
            
            # Потенциальные корреляции и инсайты
            correlation_insights = [
                {
                    'Инсайт': 'Влияние типа автора',
                    'Описание': 'Официальные аккаунты и CEO имеют наибольшее влияние на движение токенов',
                    'Потенциал': 'Высокий',
                    'Рекомендация': 'Мониторить твиты верифицированных аккаунтов с >100k подписчиков'
                },
                {
                    'Инсайт': 'Временной фактор',
                    'Описание': 'Твиты в первые 6 часов после создания токена имеют максимальное влияние',
                    'Потенциал': 'Очень высокий',
                    'Рекомендация': 'Приоритезировать мониторинг новых токенов (< 6 часов)'
                },
                {
                    'Инсайт': 'Engagement качество',
                    'Описание': 'Авторы с высоким engagement rate (лайки/твиты) дают качественные сигналы',
                    'Потенциал': 'Средний',
                    'Рекомендация': 'Фильтровать авторов по качеству engagement (>2.0 ratio)'
                },
                {
                    'Инсайт': 'Верификация важна',
                    'Описание': 'Верифицированные аккаунты создают более сильные движения цены',
                    'Потенциал': 'Высокий',
                    'Рекомендация': 'Отдавать приоритет твитам от верифицированных аккаунтов'
                }
            ]
            
            # Создаем DataFrame'ы
            main_df = pd.DataFrame(main_analysis)
            author_df = pd.DataFrame(author_summary)
            type_df = pd.DataFrame(author_type_analysis)
            insights_df = pd.DataFrame(correlation_insights)
            
            # Сохраняем в Excel
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                main_df.to_excel(writer, sheet_name='Основной анализ', index=False)
                author_df.to_excel(writer, sheet_name='Авторы', index=False)
                type_df.to_excel(writer, sheet_name='Типы авторов', index=False)
                insights_df.to_excel(writer, sheet_name='Инсайты', index=False)
                
                # Статистика
                stats_data = [
                    {'Метрика': 'Всего проанализировано токенов', 'Значение': len(set(r['token'].id for r in results))},
                    {'Метрика': 'Всего твитов проанализировано', 'Значение': len(results)},
                    {'Метрика': 'Уникальных авторов', 'Значение': len(unique_authors)},
                    {'Метрика': 'Верифицированных авторов', 'Значение': sum(1 for r in results if r['author_data']['is_verified'])},
                    {'Метрика': 'Средние подписчики', 'Значение': f"{sum(r['author_data']['followers_count'] for r in results) / len(results):,.0f}"},
                    {'Метрика': 'Максимум подписчиков', 'Значение': f"{max(r['author_data']['followers_count'] for r in results):,}"},
                    {'Метрика': 'Дата анализа', 'Значение': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                ]
                
                stats_df = pd.DataFrame(stats_data)
                stats_df.to_excel(writer, sheet_name='Статистика', index=False)
                
                # Автоподгонка ширины колонок
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except:
                                pass
                        adjusted_width = min(max_length + 2, 50)
                        worksheet.column_dimensions[column_letter].width = adjusted_width
                    
                    worksheet.freeze_panes = 'A2'
            
            logger.info(f"✅ Демонстрационный анализ сохранен в {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания Excel: {e}")
            return None

async def main():
    """Главная функция демо-анализа"""
    logger.info("🚀 Запуск демонстрационного анализа корреляций Twitter авторов")
    
    analyzer = DemoTwitterAnalyzer()
    
    # Анализируем твиты с реальными профилями авторов
    results = await analyzer.analyze_sample_tweets_with_authors()
    
    if not results:
        logger.error("❌ Нет результатов для анализа")
        return
    
    logger.info(f"📊 Проанализировано {len(results)} твитов с профилями авторов")
    
    # Создаем отчет
    filename = analyzer.create_demo_analysis_excel(results)
    
    if filename:
        logger.info(f"📈 ДЕМОНСТРАЦИОННЫЙ АНАЛИЗ КОРРЕЛЯЦИЙ:")
        logger.info(f"  • Файл: {filename}")
        logger.info(f"  • Твитов: {len(results)}")
        
        # Статистика по типам авторов
        type_stats = {}
        total_followers = 0
        verified_count = 0
        
        for result in results:
            author_type = result['author_type']
            author_data = result['author_data']
            
            if author_type not in type_stats:
                type_stats[author_type] = 0
            type_stats[author_type] += 1
            
            total_followers += author_data['followers_count']
            if author_data['is_verified']:
                verified_count += 1
        
        logger.info(f"  • Средние подписчики: {total_followers / len(results):,.0f}")
        logger.info(f"  • Верифицированных: {verified_count}/{len(results)}")
        logger.info(f"  • Типы авторов: {dict(type_stats)}")
    
    logger.info("✅ Демонстрационный анализ завершен!")

if __name__ == "__main__":
    asyncio.run(main()) 